"""
AgentGraph Intelligence - Adaptive Scanner
Auto-selects scan strategy based on project size and characteristics.
Small projects (<100 files) → single-threaded (no overhead)
Medium projects (100-2k files) → multi-threaded
Large projects (2k+ files) → multi-process with streaming
"""

import time
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database import GraphDatabase
from __init__ import ParserRegistry, CodebaseScanner


class AdaptiveScanner:
    """
    Production scanner that adapts to project size:
    - 1-50 files   : Single-threaded (fastest, no overhead)
    - 50-500 files : Multi-threaded (4-8 workers)
    - 500+ files   : Multi-process + batch DB inserts (prevents GIL contention)
    """

    def __init__(self, db: Optional[GraphDatabase] = None,
                 root: Optional[str] = None,
                 config: Optional[Dict] = None):
        self.db     = db or GraphDatabase()
        self.root   = root
        self.config = config or {}
        self.base_scanner = CodebaseScanner(db=self.db, root=root)
        ParserRegistry.init_all()

    # ────────────────────────────────────────────
    # Main API
    # ────────────────────────────────────────────

    def scan(self, root: Optional[str] = None,
             mode: str = "auto",
             workers: int = 4,
             stream_results: bool = False) -> Dict[str, Any]:
        """
        Scan with adaptive strategy selection.
        
        mode: "auto" | "sequential" | "threaded" | "process" | "stream"
        workers: Thread/process pool size
        stream_results: If True, yield results instead of returning
        """
        root = root or self.root or os.getcwd()
        root_path = Path(root).resolve()

        # Collect files
        files, skipped = self._collect_files(root_path)
        total = len(files)

        if not files:
            return {"status": "no_files", "root": str(root_path), "errors": []}

        # Auto-select mode
        if mode == "auto":
            if total < 50:
                mode = "sequential"
            elif total < 500:
                mode = "threaded"
            else:
                mode = "process"

        t0 = time.time()

        # Dispatch
        if mode == "sequential":
            result = self._scan_sequential(files)
        elif mode == "threaded":
            result = self._scan_threaded(files, workers)
        elif mode in ("process", "stream"):
            result = self._scan_process(files, workers)
        else:
            result = self._scan_sequential(files)

        # Persist
        nodes, edges = result["nodes"], result["edges"]
        if nodes or edges:
            self.db.upsert_nodes_batch(nodes)
            self.db.upsert_edges_batch(edges)

        duration = time.time() - t0
        self.db.log_scan(str(root_path), total, len(nodes), len(edges), duration)

        return {
            "status":       "ok",
            "root":         str(root_path),
            "files":        total,
            "skipped":      skipped,
            "nodes":        len(nodes),
            "edges":        len(edges),
            "errors":       result.get("errors", []),
            "duration_s":   round(duration, 3),
            "mode":         mode,
        }

    # ────────────────────────────────────────────
    # File collection
    # ────────────────────────────────────────────

    def _collect_files(self, root_path: Path) -> Tuple[List[str], int]:
        files, skipped = [], 0
        for dirpath, dirnames, filenames in os.walk(root_path):
            from __init__ import IGNORE_DIRS
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in ParserRegistry.supported_extensions():
                    files.append(str(Path(dirpath) / fname))
                else:
                    skipped += 1
        return files, skipped

    # ────────────────────────────────────────────
    # Sequential
    # ────────────────────────────────────────────

    def _scan_sequential(self, files: List[str]) -> Dict[str, Any]:
        nodes, edges, errors = [], [], []
        scanned_files = set()
        for f in files:
            scanned_files.add(f)
            # Hash check - skip if unchanged
            if self.config.get("SCAN_CACHE", True) and not self.db.is_file_changed(f):
                continue
            # Clear old data for this file
            self.db.clear_file(f)
            try:
                n, e, err = self.base_scanner._scan_single(f)
                nodes += n; edges += e; errors += err
            except Exception as exc:
                errors.append(f"{f}: {exc}")

        # Cleanup: remove database entries for files no longer present in this scan
        self._cleanup_missing_files(scanned_files)
        return {"nodes": nodes, "edges": edges, "errors": errors}

    # ────────────────────────────────────────────
    # Threaded
    # ────────────────────────────────────────────

    def _scan_threaded(self, files: List[str], workers: int) -> Dict[str, Any]:
        nodes, edges, errors = [], [], []
        scanned_files = set()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # Pre-filter unchanged files
            to_scan = []
            for f in files:
                scanned_files.add(f)
                if self.config.get("SCAN_CACHE", True) and not self.db.is_file_changed(f):
                    continue
                self.db.clear_file(f)
                to_scan.append(f)

            futures = {pool.submit(self.base_scanner._scan_single, f): f for f in to_scan}
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    n, e, err = future.result()
                    nodes += n; edges += e; errors += err
                except Exception as exc:
                    errors.append(f"{file_path}: {exc}")

        self._cleanup_missing_files(scanned_files)
        return {"nodes": nodes, "edges": edges, "errors": errors}

    # ────────────────────────────────────────────
    # Process pool
    # ────────────────────────────────────────────

    def _scan_process(self, files: List[str], workers: int) -> Dict[str, Any]:
        """
        Multi-process scan for large projects.
        Uses spawn to avoid GIL contention.
        """
        nodes, edges, errors = [], [], []
        scanned_files = set()
        to_scan = []
        # Pre-filter and clear in main process
        for f in files:
            scanned_files.add(f)
            if self.config.get("SCAN_CACHE", True) and not self.db.is_file_changed(f):
                continue
            self.db.clear_file(f)
            to_scan.append(f)

        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_parse_one, f, self.root or os.getcwd()): f for f in to_scan}
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    result = future.result()
                    nodes += result.get("nodes", [])
                    edges += result.get("edges", [])
                    errors += result.get("errors", [])
                except Exception as exc:
                    errors.append(f"{file_path}: {exc}")

        self._cleanup_missing_files(scanned_files)
        return {"nodes": nodes, "edges": edges, "errors": errors}

    # ────────────────────────────────────────────
    # Single-file scan (for file watcher compatibility)
    # ────────────────────────────────────────────

    def scan_file(self, file_path: str) -> Dict[str, Any]:
        """Scan a single file and persist to database."""
        try:
            nodes, edges, errors = self.base_scanner._scan_single(file_path)
            if nodes or edges:
                self.db.upsert_nodes_batch(nodes)
                self.db.upsert_edges_batch(edges)
            return {"nodes": nodes, "edges": edges, "errors": errors}
        except Exception as exc:
            return {"nodes": [], "edges": [], "errors": [str(exc)]}

    def on_file_change(self, file_path: str):
        """Handle live file changes (called by FileWatcher)."""
        # Skip if file hasn't actually changed (prevents redundant work)
        if not self.db.is_file_changed(file_path):
            return
        self.db.clear_file(file_path)
        try:
            result = self.scan_file(file_path)
            if result.get("nodes") or result.get("edges"):
                self.db.record_file_hash(file_path)
        except Exception:
            pass


    def _cleanup_missing_files(self, scanned_files: set):
        """Remove database entries for files that were not found during this scan."""
        root = self.root or os.getcwd()
        root_path = str(Path(root).resolve())
        conn = self.db._get_conn()
        db_files = conn.execute(
            "SELECT DISTINCT file FROM nodes WHERE file LIKE ?",
            (root_path + '%',)
        ).fetchall()
        for (db_file,) in db_files:
            if db_file not in scanned_files:
                self.db.clear_file(db_file)

# ────────────────────────────────────────────
# Module-level helper for process pool
# ────────────────────────────────────────────

def _parse_one(file_path: str, project_root: str) -> Dict[str, Any]:
    """Helper for ProcessPoolExecutor - must be picklable."""
    from __init__ import ParserRegistry
    parser = ParserRegistry.get_parser(file_path)
    if not parser:
        return {"nodes": [], "edges": [], "errors": ["No parser available"]}
    return parser.parse(file_path, root_path=project_root)
