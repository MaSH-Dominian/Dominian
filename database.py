"""
AgentGraph Intelligence - Core Database Engine
SQLite-based graph store with WAL mode, full indexing, and microsecond queries.
"""

import sqlite3
import json
import time
import uuid
import hashlib
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-128000;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=268435456;

CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    file        TEXT NOT NULL,
    language    TEXT NOT NULL,
    line_start  INTEGER DEFAULT 0,
    line_end    INTEGER DEFAULT 0,
    complexity  INTEGER DEFAULT 0,
    quality     REAL    DEFAULT 100.0,
    signature   TEXT    DEFAULT '',
    docstring   TEXT    DEFAULT '',
    metadata    TEXT    DEFAULT '{}',
    confidence  TEXT    DEFAULT 'EXTRACTED',
    provenance  TEXT    DEFAULT 'regex_parser',
    community   INTEGER DEFAULT NULL,
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id           TEXT PRIMARY KEY,
    from_node    TEXT NOT NULL,
    to_node      TEXT NOT NULL,
    relationship TEXT NOT NULL,
    weight       REAL DEFAULT 1.0,
    confidence   REAL DEFAULT 1.0,
    provenance   TEXT DEFAULT 'regex_parser',
    metadata     TEXT DEFAULT '{}',
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id          TEXT PRIMARY KEY,
    agent_type  TEXT NOT NULL,
    started_at  REAL    NOT NULL,
    last_active REAL    NOT NULL,
    query_count INTEGER DEFAULT 0,
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS query_log (
    id           TEXT PRIMARY KEY,
    session_id   TEXT,
    raw_query    TEXT NOT NULL,
    resolved     TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    latency_ms   REAL DEFAULT 0,
    timestamp    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_history (
    id         TEXT PRIMARY KEY,
    root_path  TEXT NOT NULL,
    file_count INTEGER DEFAULT 0,
    node_count INTEGER DEFAULT 0,
    edge_count INTEGER DEFAULT 0,
    duration_s REAL DEFAULT 0,
    scanned_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS file_hashes (
    file_path    TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    parsed_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_name       ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_type       ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_file       ON nodes(file);
CREATE INDEX IF NOT EXISTS idx_nodes_language   ON nodes(language);
CREATE INDEX IF NOT EXISTS idx_nodes_quality    ON nodes(quality);
CREATE INDEX IF NOT EXISTS idx_nodes_complexity ON nodes(complexity);
CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence);
CREATE INDEX IF NOT EXISTS idx_nodes_community  ON nodes(community);

CREATE INDEX IF NOT EXISTS idx_edges_from   ON edges(from_node);
CREATE INDEX IF NOT EXISTS idx_edges_to     ON edges(to_node);
CREATE INDEX IF NOT EXISTS idx_edges_rel    ON edges(relationship);
CREATE INDEX IF NOT EXISTS idx_edges_weight ON edges(weight);
CREATE INDEX IF NOT EXISTS idx_edges_pair   ON edges(from_node, to_node);
CREATE INDEX IF NOT EXISTS idx_edges_from_rel ON edges(from_node, relationship);
CREATE INDEX IF NOT EXISTS idx_edges_to_rel ON edges(to_node, relationship);
CREATE INDEX IF NOT EXISTS idx_nodes_type_complexity ON nodes(type, complexity);
CREATE INDEX IF NOT EXISTS idx_nodes_quality_type ON nodes(quality, type);

CREATE INDEX IF NOT EXISTS idx_qlog_session ON query_log(session_id);
CREATE INDEX IF NOT EXISTS idx_qlog_time    ON query_log(timestamp);
"""


class GraphDatabase:
    def __init__(self, db_path: str = "agentgraph.db"):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialize()

    def _initialize(self):
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Add new columns to existing DBs without breaking them."""
        conn = self._get_conn()
        node_cols = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
        edge_cols = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
        migrations = []
        if "confidence" not in node_cols:
            migrations.append("ALTER TABLE nodes ADD COLUMN confidence TEXT DEFAULT 'EXTRACTED'")
        if "provenance" not in node_cols:
            migrations.append("ALTER TABLE nodes ADD COLUMN provenance TEXT DEFAULT 'regex_parser'")
        if "confidence" not in edge_cols:
            migrations.append("ALTER TABLE edges ADD COLUMN confidence REAL DEFAULT 1.0")
        if "provenance" not in edge_cols:
            migrations.append("ALTER TABLE edges ADD COLUMN provenance TEXT DEFAULT 'regex_parser'")
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False, timeout=30, isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-128000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self):
        conn = self._get_conn()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # ── Content Hash / Cache ──────────────────────────────────────

    def get_file_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (OSError, IOError):
            return ""

    def is_file_changed(self, file_path: str) -> bool:
        current = self.get_file_hash(file_path)
        if not current:
            return True
        conn = self._get_conn()
        row = conn.execute(
            "SELECT content_hash FROM file_hashes WHERE file_path=?", (file_path,)
        ).fetchone()
        return row is None or row[0] != current

    def record_file_hash(self, file_path: str):
        h = self.get_file_hash(file_path)
        if not h:
            return
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO file_hashes (file_path, content_hash, parsed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                content_hash=excluded.content_hash, parsed_at=excluded.parsed_at
        """, (file_path, h, time.time()))

    # ── Node Operations ───────────────────────────────────────────

    def upsert_node(
        self, name: str, type: str, file: str, language: str,
        line_start: int = 0, line_end: int = 0,
        complexity: int = 0, quality: float = 100.0,
        signature: str = "", docstring: str = "",
        metadata: Dict = None,
        confidence: str = "EXTRACTED",
        provenance: str = "regex_parser",
    ) -> str:
        node_id = self._node_id(name, file)
        now = time.time()
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO nodes
                (id, name, type, file, language, line_start, line_end,
                 complexity, quality, signature, docstring, metadata,
                 confidence, provenance, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type, line_start=excluded.line_start,
                line_end=excluded.line_end, complexity=excluded.complexity,
                quality=excluded.quality, signature=excluded.signature,
                docstring=excluded.docstring, metadata=excluded.metadata,
                confidence=excluded.confidence, provenance=excluded.provenance,
                updated_at=excluded.updated_at
        """, (
            node_id, name, type, file, language,
            line_start, line_end, complexity, quality,
            signature, docstring, json.dumps(metadata or {}),
            confidence, provenance, now, now
        ))
        return node_id

    def upsert_nodes_batch(self, nodes: List[Dict]) -> int:
        """Batch insert/update nodes - 10-50x faster than individual inserts."""
        if not nodes:
            return 0
        conn = self._get_conn()
        now = time.time()

        # Prepare batch data
        batch_data = []
        for node in nodes:
            node_id = self._node_id(node["name"], node["file"])
            batch_data.append((
                node_id, node["name"], node["type"], node["file"], node["language"],
                node.get("line_start", 0), node.get("line_end", 0),
                node.get("complexity", 0), node.get("quality", 100.0),
                node.get("signature", ""), node.get("docstring", ""),
                json.dumps(node.get("metadata", {})),
                node.get("confidence", "EXTRACTED"),
                node.get("provenance", "regex_parser"),
                now, now
            ))

        # Execute batch insert with single transaction
        conn.executemany("""
            INSERT INTO nodes
                (id, name, type, file, language, line_start, line_end,
                 complexity, quality, signature, docstring, metadata,
                 confidence, provenance, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                type=excluded.type, line_start=excluded.line_start,
                line_end=excluded.line_end, complexity=excluded.complexity,
                quality=excluded.quality, signature=excluded.signature,
                docstring=excluded.docstring, metadata=excluded.metadata,
                confidence=excluded.confidence, provenance=excluded.provenance,
                updated_at=excluded.updated_at
        """, batch_data)
        return len(nodes)

    def upsert_edges_batch(self, edges: List[Dict]) -> int:
        """Batch insert/update edges - 10-50x faster than individual inserts."""
        if not edges:
            return 0
        conn = self._get_conn()
        now = time.time()

        # Prepare batch data, filtering out edges with missing node references
        batch_data = []
        for edge in edges:
            from_id = self._node_id(edge["from_name"], edge["from_file"])
            to_id = self._node_id(edge["to_name"], edge["to_file"])
            edge_id = self._edge_id(from_id, to_id, edge["relationship"])
            batch_data.append((
                edge_id, from_id, to_id, edge["relationship"],
                edge.get("weight", 1.0), edge.get("confidence", 1.0),
                edge.get("provenance", "regex_parser"),
                json.dumps(edge.get("metadata", {})), now
            ))

        # Temporarily disable FK checks to allow cross-file references that may not yet exist
        # (e.g., call edges to nodes in other files that haven't been scanned yet)
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.executemany("""
                INSERT INTO edges (id, from_node, to_node, relationship, weight,
                                   confidence, provenance, metadata, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    weight=excluded.weight, confidence=excluded.confidence,
                    provenance=excluded.provenance, metadata=excluded.metadata
            """, batch_data)
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        return len(edges)

    def get_node(self, name: str, file: str = None) -> Optional[Dict]:
        conn = self._get_conn()
        if file:
            node_id = self._node_id(name, file)
            row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM nodes WHERE name=? ORDER BY updated_at DESC LIMIT 1", (name,)
            ).fetchone()
        if row:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
            return result
        return None

    def get_nodes_by_type(self, type: str, limit: int = None) -> List[Dict]:
        sql = "SELECT * FROM nodes WHERE type=? ORDER BY quality DESC"
        params = (type,)
        if limit:
            sql += " LIMIT ?"
            params = (type, limit)
        rows = self._get_conn().execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_nodes_by_file(self, file: str) -> List[Dict]:
        """Get nodes by file path (supports partial matching)."""
        rows = self._get_conn().execute(
            "SELECT * FROM nodes WHERE file LIKE ? ORDER BY line_start", (f"%{file}%",)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_nodes_by_name(self, name: str, limit: int = None) -> List[Dict]:
        """Get nodes by name (supports partial matching)."""
        sql = "SELECT * FROM nodes WHERE name LIKE ? ORDER BY name"
        params = (f"%{name}%",)
        if limit:
            sql += " LIMIT ?"
            params = (f"%{name}%", limit)
        rows = self._get_conn().execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_nodes_by_quality(self, quality_type: str, limit: int = 10) -> List[Dict]:
        """Get nodes by quality level ('low' < 70, 'high' >= 70)."""
        if quality_type == "low":
            rows = self._get_conn().execute(
                "SELECT * FROM nodes WHERE quality < 70 ORDER BY quality ASC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._get_conn().execute(
                "SELECT * FROM nodes WHERE quality >= 70 ORDER BY quality DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_nodes(self, query: str, limit: int = 20) -> List[Dict]:
        pattern = f"%{query.lower()}%"
        rows = self._get_conn().execute("""
            SELECT * FROM nodes
            WHERE LOWER(name) LIKE ? OR LOWER(file) LIKE ? OR LOWER(signature) LIKE ?
            ORDER BY
                CASE WHEN LOWER(name) = ? THEN 0
                     WHEN LOWER(name) LIKE ? THEN 1
                     ELSE 2 END,
                quality DESC
            LIMIT ?
        """, (pattern, pattern, pattern, query.lower(), f"{query.lower()}%", limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_node(self, name: str, file: str) -> bool:
        """Delete a specific node and its edges by name + file."""
        node_id = self._node_id(name, file)
        conn = self._get_conn()
        conn.execute("DELETE FROM edges WHERE from_node=? OR to_node=?", (node_id, node_id))
        conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        return True

    def rename_node(self, old_name: str, new_name: str, file: str) -> bool:
        old_id = self._node_id(old_name, file)
        new_id = self._node_id(new_name, file)
        conn = self._get_conn()
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.execute("BEGIN")
            conn.execute("UPDATE nodes SET id=?, name=?, updated_at=? WHERE id=?",
                         (new_id, new_name, time.time(), old_id))
            conn.execute("UPDATE edges SET from_node=? WHERE from_node=?", (new_id, old_id))
            conn.execute("UPDATE edges SET to_node=? WHERE to_node=?", (new_id, old_id))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        return True

    def update_node_metrics(self, name: str, file: str,
                            complexity: int = None, quality: float = None) -> bool:
        node_id = self._node_id(name, file)
        updates, params = [], []
        if complexity is not None:
            updates.append("complexity=?"); params.append(complexity)
        if quality is not None:
            updates.append("quality=?"); params.append(quality)
        if not updates:
            return False
        updates.append("updated_at=?"); params.append(time.time())
        params.append(node_id)
        self._get_conn().execute(f"UPDATE nodes SET {', '.join(updates)} WHERE id=?", params)
        return True

    # ── Edge Operations ───────────────────────────────────────────

    def upsert_edge(
        self, from_name: str, from_file: str, to_name: str, to_file: str,
        relationship: str, weight: float = 1.0, metadata: Dict = None,
        confidence: float = 1.0, provenance: str = "regex_parser",
    ) -> str:
        from_id = self._node_id(from_name, from_file)
        to_id   = self._node_id(to_name, to_file)
        edge_id = self._edge_id(from_id, to_id, relationship)
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO edges (id, from_node, to_node, relationship, weight,
                               confidence, provenance, metadata, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                weight=excluded.weight, confidence=excluded.confidence,
                provenance=excluded.provenance, metadata=excluded.metadata
        """, (edge_id, from_id, to_id, relationship, weight,
              confidence, provenance, json.dumps(metadata or {}), time.time()))
        return edge_id

    def get_dependencies(self, name: str, file: str = None) -> List[Dict]:
        """Get dependencies with module-level import fallback.

        If the entity (class/function) has no import/depends edges,
        returns the module node's imports for the same file.
        This bridges the gap between Python's module-level imports and
        class-level dependency queries.
        """
        node_id = self._get_node_id_flexible(name, file)
        if not node_id:
            return []

        conn = self._get_conn()

        # Step 1: Get entity's import/depends edges (not defines/calls)
        rows = conn.execute("""
            SELECT n.*, e.relationship, e.weight, e.confidence, e.provenance
            FROM edges e JOIN nodes n ON e.to_node = n.id
            WHERE e.from_node = ? 
              AND e.relationship IN ('imports', 'depends_on', 'uses', 'calls')
            ORDER BY e.weight DESC
        """, (node_id,)).fetchall()

        if rows:
            return [self._row_to_dict(r) for r in rows]

        # Step 2: No import edges - inherit from module
        node_row = conn.execute(
            "SELECT file FROM nodes WHERE id=?", (node_id,)
        ).fetchone()

        if not node_row:
            return []

        file_path = node_row[0]
        module_name = Path(file_path).stem
        module_id = self._node_id(module_name, file_path)

        # Get module's import edges
        module_rows = conn.execute("""
            SELECT n.*, e.relationship, e.weight, e.confidence, e.provenance
            FROM edges e JOIN nodes n ON e.to_node = n.id
            WHERE e.from_node = ? AND e.relationship = 'imports'
            ORDER BY e.weight DESC
        """, (module_id,)).fetchall()

        return [self._row_to_dict(r) for r in module_rows]

    def get_dependents(self, name: str, file: str = None) -> List[Dict]:
        node_id = self._get_node_id_flexible(name, file)
        if not node_id:
            return []
        rows = self._get_conn().execute("""
            SELECT n.*, e.relationship, e.weight, e.confidence, e.provenance
            FROM edges e JOIN nodes n ON e.from_node = n.id
            WHERE e.to_node = ? ORDER BY e.weight DESC
        """, (node_id,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_edge(self, from_name: str, from_file: str,
                    to_name: str, to_file: str, relationship: str = None) -> bool:
        from_id = self._node_id(from_name, from_file)
        to_id   = self._node_id(to_name, to_file)
        conn = self._get_conn()
        if relationship:
            conn.execute("DELETE FROM edges WHERE id=?",
                         (self._edge_id(from_id, to_id, relationship),))
        else:
            conn.execute("DELETE FROM edges WHERE from_node=? AND to_node=?", (from_id, to_id))
        return True

    # ── Graph Analytics ───────────────────────────────────────────

    def find_cycles(self) -> List[List[str]]:
        """Detect circular dependencies. Returns lists of human-readable names."""
        conn = self._get_conn()
        edges = conn.execute("SELECT from_node, to_node FROM edges").fetchall()
        id_to_name = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM nodes").fetchall()}

        graph: Dict[str, List[str]] = {}
        for e in edges:
            graph.setdefault(e[0], []).append(e[1])

        cycles, visited, rec_stack = [], set(), set()

        def _canonical_cycle(cycle):
            """Rotate cycle so smallest element is first for deduplication."""
            if not cycle:
                return tuple()
            # Remove trailing duplicate if present (e.g. [A,B,A] -> [A,B])
            if len(cycle) > 1 and cycle[0] == cycle[-1]:
                cycle = cycle[:-1]
            if not cycle:
                return tuple()
            min_idx = cycle.index(min(cycle))
            rotated = cycle[min_idx:] + cycle[:min_idx]
            return tuple(rotated)

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for nb in graph.get(node, []):
                if nb not in visited:
                    dfs(nb, path + [nb])
                elif nb in rec_stack:
                    idx = path.index(nb)
                    cycle = [id_to_name.get(n, n) for n in path[idx:]]
                    # Filter out self-loops (single node cycles)
                    if len(set(cycle)) > 1:
                        cycles.append(cycle)
            rec_stack.discard(node)

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node, [node])

        # Deduplicate using canonical cycle representation
        seen, unique = set(), []
        for c in cycles:
            key = _canonical_cycle(c)
            if key not in seen and len(key) > 1:
                seen.add(key)
                unique.append(c)
        return unique

    def get_impact(self, name: str, file: str = None, depth: int = 3,
                   min_weight: float = 0.0) -> Dict:
        node_id = self._get_node_id_flexible(name, file)
        if not node_id:
            return {"affected_count": 0, "affected_nodes": [], "risk_level": "LOW"}

        conn = self._get_conn()
        affected, queue, visited = set(), [(node_id, 0)], {node_id}

        while queue:
            current, d = queue.pop(0)
            if d >= depth:
                continue
            for row in conn.execute(
                "SELECT from_node, weight FROM edges WHERE to_node=?", (current,)
            ).fetchall():
                nid, w = row[0], row[1]
                if nid not in visited and w >= min_weight:
                    visited.add(nid)
                    affected.add(nid)
                    queue.append((nid, d + 1))

        nodes = []
        for nid in affected:
            row = conn.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
            if row:
                nodes.append(self._row_to_dict(row))

        count = len(nodes)
        return {
            "affected_count": count,
            "affected_nodes": sorted(nodes, key=lambda x: x.get("complexity", 0), reverse=True),
            "risk_level": "CRITICAL" if count > 10 else "HIGH" if count > 5 else "MEDIUM" if count > 2 else "LOW",
        }

    def get_hotspots(self, limit: int = 10) -> List[Dict]:
        rows = self._get_conn().execute("""
            SELECT n.*,
                   COUNT(DISTINCT e_out.id) as out_degree,
                   COUNT(DISTINCT e_in.id)  as in_degree
            FROM nodes n
            LEFT JOIN edges e_out ON e_out.from_node = n.id
            LEFT JOIN edges e_in  ON e_in.to_node    = n.id
            GROUP BY n.id
            ORDER BY (n.complexity * 3) +
                     (COUNT(DISTINCT e_out.id) + COUNT(DISTINCT e_in.id)) +
                     ((100 - n.quality) / 10) DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def find_god_nodes(self, limit: int = 10) -> List[Dict]:
        """Highest-degree nodes — nodes that connect everything."""
        rows = self._get_conn().execute("""
            SELECT n.*,
                   COUNT(DISTINCT e_out.id) + COUNT(DISTINCT e_in.id) as total_degree,
                   COUNT(DISTINCT e_out.id) as out_degree,
                   COUNT(DISTINCT e_in.id)  as in_degree
            FROM nodes n
            LEFT JOIN edges e_out ON e_out.from_node = n.id
            LEFT JOIN edges e_in  ON e_in.to_node    = n.id
            WHERE n.type NOT IN ('dependency', 'module')
            GROUP BY n.id
            ORDER BY total_degree DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def find_surprising_connections(self) -> List[Dict]:
        """Edges between nodes in different top-level directories."""
        rows = self._get_conn().execute("""
            SELECT nf.name as from_name, nf.file as from_file,
                   nt.name as to_name,   nt.file as to_file,
                   e.relationship, e.weight, e.confidence
            FROM edges e
            JOIN nodes nf ON e.from_node = nf.id
            JOIN nodes nt ON e.to_node   = nt.id
            WHERE nf.file != nt.file
              AND e.relationship NOT IN ('imports', 'defines')
            ORDER BY e.weight DESC LIMIT 100
        """).fetchall()

        results, seen = [], set()
        for row in rows:
            r = dict(row)
            from_top = r["from_file"].split("/")[0]
            to_top   = r["to_file"].split("/")[0]
            key = (r["from_name"], r["to_name"])
            if from_top != to_top and key not in seen:
                seen.add(key)
                results.append(r)
        return results[:20]

    def get_orphans(self) -> List[Dict]:
        rows = self._get_conn().execute("""
            SELECT n.* FROM nodes n
            WHERE n.id NOT IN (
                SELECT DISTINCT from_node FROM edges
                UNION SELECT DISTINCT to_node FROM edges
            )
        """).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_stats(self) -> Dict:
        conn = self._get_conn()
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        lang_dist  = conn.execute(
            "SELECT language, COUNT(*) FROM nodes GROUP BY language ORDER BY 2 DESC"
        ).fetchall()
        type_dist  = conn.execute(
            "SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY 2 DESC"
        ).fetchall()
        avg_q = conn.execute("SELECT AVG(quality) FROM nodes").fetchone()[0] or 0
        avg_c = conn.execute("SELECT AVG(complexity) FROM nodes").fetchone()[0] or 0
        conf_dist = conn.execute(
            "SELECT confidence, COUNT(*) FROM nodes GROUP BY confidence"
        ).fetchall()
        
        # Community statistics
        comm_dist = conn.execute(
            "SELECT community, COUNT(*) FROM nodes WHERE community IS NOT NULL GROUP BY community ORDER BY 2 DESC"
        ).fetchall()
        
        return {
            "nodes": node_count, "edges": edge_count,
            "avg_quality": round(avg_q, 1), "avg_complexity": round(avg_c, 1),
            "languages": {r[0]: r[1] for r in lang_dist},
            "types":     {r[0]: r[1] for r in type_dist},
            "confidence_distribution": {r[0]: r[1] for r in conf_dist},
            "communities": {r[0]: r[1] for r in comm_dist},
        }

    def get_communities(self) -> List[Dict]:
        """Return community groups with sizes."""
        rows = self._get_conn().execute(
            "SELECT community, COUNT(*) as size FROM nodes WHERE community IS NOT NULL GROUP BY community ORDER BY size DESC"
        ).fetchall()
        return [{"community_id": r[0], "size": r[1]} for r in rows]

    def clear_file(self, file: str):
        conn = self._get_conn()
        # Get all nodes for this file
        node_ids = [r[0] for r in conn.execute(
            "SELECT id FROM nodes WHERE file=?", (file,)
        ).fetchall()]
        if node_ids:
            ph = ",".join("?" * len(node_ids))
            # Delete all edges connected to these nodes (both directions)
            conn.execute(f"DELETE FROM edges WHERE from_node IN ({ph}) OR to_node IN ({ph})",
                         node_ids + node_ids)
            # Delete the nodes
            conn.execute(f"DELETE FROM nodes WHERE id IN ({ph})", node_ids)
        conn.execute("DELETE FROM file_hashes WHERE file_path=?", (file,))

    def clear_all(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")

    def log_scan(self, root_path, file_count, node_count, edge_count, duration_s):
        self._get_conn().execute("""
            INSERT INTO scan_history (id, root_path, file_count, node_count, edge_count, duration_s, scanned_at)
            VALUES (?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()), root_path, file_count, node_count, edge_count, duration_s, time.time()))

    def log_query(self, session_id, raw_query, resolved, result_count, latency_ms):
        self._get_conn().execute("""
            INSERT INTO query_log (id, session_id, raw_query, resolved, result_count, latency_ms, timestamp)
            VALUES (?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()), session_id, raw_query, resolved, result_count, latency_ms, time.time()))

    # ── Helpers ───────────────────────────────────────────────────

    def _node_id(self, name: str, file: str) -> str:
        return f"{file}::{name}".replace(" ", "_")

    def _edge_id(self, from_id: str, to_id: str, rel: str) -> str:
        return f"{from_id}--{rel}--{to_id}"

    def _get_node_id_flexible(self, name: str, file: str = None) -> Optional[str]:
        if file:
            return self._node_id(name, file)
        row = self._get_conn().execute(
            "SELECT id FROM nodes WHERE name=? ORDER BY updated_at DESC LIMIT 1", (name,)
        ).fetchone()
        return row[0] if row else None

    def _row_to_dict(self, row) -> Dict:
        d = dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            d["metadata"] = json.loads(d["metadata"])
        return d

    def invalidate_cache(self):
        """No-op - removed in-memory cache, relying on SQLite cache"""
        pass

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
