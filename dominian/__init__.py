"""
AgentGraph Intelligence - Core Registry & Scanner
Zero-dependency symbol extraction for Python, JavaScript, TypeScript, Go, Rust, Java, C++.
Uses regex-based extraction as the universal fallback.
Tree-sitter parsers auto-register when tree-sitter is available.
"""

from __future__ import annotations

import ast
import glob
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

# Import from other modules
from .database import GraphDatabase
from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .other_parsers import JavaParser, GoParser, RustParser, CppParser
from .tree_sitter_parser import (
    TreeSitterParser, TreeSitterRegistry, _TS_REGISTRY_AVAILABLE, get_global_registry
)


__all__ = [
    "ParserRegistry", "CodebaseScanner", "GlobalConfig",
]


# Default patterns for file scanning
IGNORE_DIRS = {
    "node_modules", "vendor", "dist", "build", "target",
    ".git", ".svn", ".hg", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", "htmlcov", "venv", ".venv",
    "site-packages", ".egg-info", "egg-info",  # exact names only
}


class GlobalConfig:
    """Global configuration shared across all components."""
    SCAN_CACHE    = True   # Use content-hash caching
    STREAM_OUTPUT = False  # Return data or print
    SAVE_DB       = True   # Persist to SQLite
    WATCH_LIVE    = False  # Auto-update on file changes
    WATCH_DELAY   = 5.0


class ParserRegistry:
    """
    Central registry: maps file extensions -> parser classes.
    Parsers registered manually OR auto-detected via tree-sitter.
    """

    _parsers: Dict[str, Type] = {}
    _extensions: Dict[str, str] = {}  # ext -> language

    @classmethod
    def register(cls, parser_class: Type):
        """Register a parser class for its declared extensions."""
        inst = parser_class()
        for ext in getattr(inst, "EXTENSIONS", set()):
            cls._parsers[ext] = parser_class
            cls._extensions[ext] = getattr(inst, "LANGUAGE", "unknown")
        return parser_class

    @classmethod
    def get_parser(cls, file_path: str) -> Optional[Any]:
        ext = Path(file_path).suffix.lower()
        pcls = cls._parsers.get(ext)
        if pcls:
            return pcls()
        return None

    @classmethod
    def supported_extensions(cls) -> List[str]:
        return sorted(cls._parsers.keys())

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Check if a file extension has a registered parser."""
        ext = Path(file_path).suffix.lower()
        return ext in cls._parsers

    @classmethod
    def _register_regex(cls, parser_class: Type):
        """Register a regex-based parser."""
        inst = parser_class()
        for ext in getattr(inst, "EXTENSIONS", set()):
            cls._parsers[ext] = parser_class
            cls._extensions[ext] = getattr(inst, "LANGUAGE", "unknown")

    @classmethod
    def _init_ts_registry(cls):
        """Auto-register tree-sitter parsers when available."""
        if _TS_REGISTRY_AVAILABLE:
            for lang, parser in get_global_registry().items():
                for ext in getattr(parser, "EXTENSIONS", set()):
                    cls._parsers[ext] = type(parser)
                    cls._extensions[ext] = lang

    @classmethod
    def init_all(cls):
        """Call once at startup. Registers regex + tree-sitter parsers."""
        cls._register_regex(PythonParser)
        cls._register_regex(JavaScriptParser)
        cls._register_regex(JavaParser)
        cls._register_regex(GoParser)
        cls._register_regex(RustParser)
        cls._register_regex(CppParser)
        cls._init_ts_registry()


class CodebaseScanner:
    """
    Scans file trees, dispatches parsers, merges into GraphDatabase.
    """

    def __init__(self, db: Optional[GraphDatabase] = None,
                 root: Optional[str] = None,
                 config: Optional[GlobalConfig] = None):
        self.db     = db or GraphDatabase()
        self.root   = root
        self.config = config or GlobalConfig()
        ParserRegistry.init_all()

    # ────────────────────────────────────────────
    # Scanning
    # ────────────────────────────────────────────

    def scan(self, root: Optional[str] = None) -> Dict[str, Any]:
        root = root or self.root or os.getcwd()
        root_path = Path(root).resolve()

        files, skipped = self._collect_files(root_path)
        if not files:
            return {"status": "no_files", "root": str(root_path), "errors": []}

        nodes, edges, errors = [], [], []
        t0 = time.time()

        for f in files:
            try:
                n, e, err = self._scan_single(f)
                nodes += n; edges += e; errors += err
            except Exception as exc:
                errors.append(f"{f}: {exc}")

        # Deduplicate edges
        edge_map = {}
        for e in edges:
            key = (e["from_name"], e["from_file"], e["to_name"], e["to_file"], e["relationship"])
            edge_map[key] = e
        edges = list(edge_map.values())

        # Batch insert into database
        if self.config.SAVE_DB:
            self.db.upsert_nodes_batch(nodes)
            self.db.upsert_edges_batch(edges)

        self.db.log_scan(str(root_path), len(files), len(nodes), len(edges), time.time() - t0)

        return {
            "status":   "ok",
            "root":     str(root_path),
            "files":    len(files),
            "skipped":  skipped,
            "nodes":    len(nodes),
            "edges":    len(edges),
            "errors":   errors,
            "duration_s": round(time.time() - t0, 3),
        }

    def _scan_single(self, file_path: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Parse one file using the best available parser."""
        # 1) Check cache
        if self.config.SCAN_CACHE and not self.db.is_file_changed(file_path):
            # File unchanged — return cached results if available
            nodes = self.db.get_nodes_by_file(file_path)
            edges = []
            return nodes, edges, ["cached"]

        # 2) Get parser (tree-sitter or regex fallback)
        parser = ParserRegistry.get_parser(file_path)

        # 3) Parse
        root = self.root or os.getcwd()
        if parser:
            result = parser.parse(file_path, root_path=root)
        else:
            result = {"nodes": [], "edges": [], "errors": ["No parser available"]}

        # 4) Record hash
        if self.config.SCAN_CACHE:
            self.db.record_file_hash(file_path)

        return result.get("nodes", []), result.get("edges", []), result.get("errors", [])

    # ────────────────────────────────────────────
    # File collection
    # ────────────────────────────────────────────

    def _collect_files(self, root_path: Path) -> Tuple[List[str], int]:
        files, skipped = [], 0
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Remove ignored dirs from traversal
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS
                and not d.startswith(".")  # hidden dirs
            ]

            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in ParserRegistry.supported_extensions():
                    files.append(str(Path(dirpath) / fname))
                else:
                    skipped += 1
        return files, skipped

    def scan_file(self, file_path: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Scan a single file and return raw results without DB persistence."""
        return self._scan_single(file_path)

    # ────────────────────────────────────────────
    # Live updates (for file watcher)
    # ────────────────────────────────────────────

    def on_file_change(self, file_path: str):
        """Called by FileWatcher when a file changes."""
        self.db.clear_file(file_path)
        try:
            nodes, edges, _ = self._scan_single(file_path)
            if nodes or edges:
                self.db.upsert_nodes_batch(nodes)
                self.db.upsert_edges_batch(edges)
                self.db.record_file_hash(file_path)
        except Exception as exc:
            pass  # Log but don't crash

    def clear_all(self):
        self.db.clear_all()
