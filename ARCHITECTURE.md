# Dominian — Architecture

## Overview

Dominian is a code intelligence tool that scans source code files, extracts structural entities (functions, classes, modules, imports) and their relationships, stores them as a directed weighted graph in SQLite, and exposes query capabilities through a CLI and an MCP server. Its primary consumer is LLM agents, which use it to understand codebase structure, dependency graphs, and refactoring risk without reading every file.

The system is split into ten modules with clear data-flow boundaries: source files enter through the scanner pipeline, become nodes and edges in the database, and leave through the formatter pipeline when queried.

```
Source files  →  AdaptiveScanner  →  ParserRegistry  →  (TreeSitterParser | RegexParser)
                                                              ↓
                                                     nodes[] + edges[]
                                                              ↓
                                               GraphDatabase.upsert_nodes_batch
                                               GraphDatabase.upsert_edges_batch
                                                              ↓
                                                          SQLite (WAL)

Query: CLI / MCP  →  Command function  →  GraphDatabase methods  →  formatter  →  Output
```


## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CONSUMERS                                      │
│                                                                             │
│   ┌──────────────────┐                          ┌────────────────────┐      │
│   │   main_new.py    │                          │    server.py       │      │
│   │   (CLI)          │                          │   (MCP Server)     │      │
│   │                  │                          │                    │      │
│   │  argparse        │                          │  FastMCP           │      │
│   │  <group> <action>│                          │  21 tools          │      │
│   │  --format flag   │                          │  2 resources       │      │
│   │                  │                          │  3 prompts         │      │
│   └────────┬─────────┘                          └────────┬───────────┘      │
│            │                                              │                  │
│            │  format_output() / _minimal()                │                  │
│            ↓                                              ↓                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         formatter.py                                │   │
│   │                                                                     │   │
│   │   format_minimal()    ~85% token reduction, agent-optimized         │   │
│   │   format_for_claude() verbose human-readable (agent format)        │   │
│   │   format_json()       machine-parseable JSON envelope              │   │
│   │                                                                     │   │
│   │   Universal locator: folder/file:name:line(type)                   │   │
│   │   Type abbrevs: fn cls mod var imp dep                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            QUERY LAYER                                      │
│                                                                             │
│   ┌──────────────────┐                                                     │
│   │   engine.py       │                                                     │
│   │   QueryEngine     │                                                     │
│   │                   │                                                     │
│   │  _detect_intent() │  "what does X depend on" → dependencies intent     │
│   │  _resolve()       │  dispatch table → resolver methods                  │
│   │  log_query()      │  latency tracking via database.query_log            │
│   └────────┬──────────┘                                                     │
│            │                                                                │
└────────────┼────────────────────────────────────────────────────────────────┘
             │
             ↓

┌─────────────────────────────────────────────────────────────────────────────┐
│                          STORAGE LAYER                                      │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                       database.py                                │      │
│   │                       GraphDatabase                              │      │
│   │                                                                  │      │
│   │  SQLite with WAL mode, 128MB cache, MEMORY temp, 256MB mmap    │      │
│   │  Thread-safe via threading.local()                               │      │
│   │                                                                  │      │
│   │  Tables: nodes | edges | agent_sessions | query_log              │      │
│   │          scan_history | file_hashes                              │      │
│   │                                                                  │      │
│   │  Batch ops: upsert_nodes_batch(), upsert_edges_batch()           │      │
│   │  Analytics: find_cycles(), get_impact(), get_hotspots(),         │      │
│   │            find_god_nodes(), find_surprising_connections(),      │      │
│   │            get_orphans(), get_stats()                            │      │
│   │                                                                  │      │
│   │  Caching: is_file_changed(), record_file_hash() (SHA-256)       │      │
│   └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          SCANNING LAYER                                     │
│                                                                             │
│   ┌───────────────────┐      ┌──────────────────────────────────────────┐   │
│   │ adaptive_scanner   │      │            __init__.py                  │   │
│   │ AdaptiveScanner    │      │                                          │   │
│   │                    │      │  ParserRegistry (ext → parser class)    │   │
│   │ <50 files:         │      │  CodebaseScanner (file tree walker)    │   │
│   │   sequential       │─────→│  GlobalConfig                           │   │
│   │ 50-500 files:      │      │  IGNORE_DIRS                            │   │
│   │   ThreadPoolExecutor│      └──────────────┬───────────────────────────┘   │
│   │ 500+ files:        │                     │                               │
│   │   ProcessPoolExecutor                    ↓                               │
│   │   (spawn method)   │      ┌──────────────────────────────────────────┐   │
│   │                    │      │         PARSERS                          │   │
│   │ Content-hash       │      │                                          │   │
│   │ cache per file     │      │  TreeSitterParser ── LanguageConfig      │   │
│   │ Cleanup of         │      │       │              (7 languages)       │   │
│   │ missing files      │      │       ↓                                  │   │
│   └───────────────────┘      │  tree_sitter_parser.py                   │   │
│                               │  tree_sitter_configs.py                  │   │
│                               │       │                                  │   │
│                               │       +── Regex parsers (fallback)      │   │
│                               │       │   PythonParser                  │   │
│                               │       │   JavaScriptParser              │   │
│                               │       │   JavaParser, GoParser,         │   │
│                               │       │   RustParser, CppParser         │   │
│                               └───────┘                                  │   │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                    import_resolver.py                            │      │
│   │                                                                  │      │
│   │  resolve_import_to_file()  →  language-specific resolvers:       │      │
│   │    resolve_python_import()   relative + absolute + src/ prefix   │      │
│   │    resolve_js_import()       relative + extensions + index       │      │
│   │    resolve_java_import()     package-based path mapping          │      │
│   │    resolve_go_import()       relative directory                  │      │
│   │    resolve_rust_use()        crate:: + self:: + super::          │      │
│   │    resolve_cpp_include()     relative + include/inc/src dirs     │      │
│   └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
```


## Module Reference

### 1. main_new.py — CLI Entry Point

The CLI uses argparse with a strict two-level command structure:

```
dominian <group> <action> [target] [options]
```

**Groups and actions:**

| Group   | Actions                              | Target          |
|---------|--------------------------------------|-----------------|
| init    | (none)                               | —               |
| scan    | (none)                               | path            |
| search  | (none)                               | query string    |
| node    | get, show                            | entity name     |
| deps    | direct, reverse                      | entity name     |
| arch    | impact, communities, cross-community | entity name     |
| graph   | stats, hotspots, cycles              | —               |
| refactor| safe, impact                         | entity name     |
| file    | functions, classes                   | file path       |
| info    | (none)                               | —               |

Every command function follows the same pattern: open database, call GraphDatabase methods, wrap results in a dict, pass to `format_output()`. No command produces output directly — all formatting is delegated to formatter.py.

The `--format` flag accepts `minimal` (default), `agent`, or `json`. The `--db-path` flag overrides the default database location (`.dominian/agentgraph.db` or the `DOMINIAN_DB` environment variable).

Aliases exist for discoverability: `node show` → `node get`, `graph circular` → `graph cycles`, `refactor safety` → `refactor safe`.

Search returns exit code 1 for empty results so agents can distinguish "found nothing" from "found something" without parsing output.

### 2. server.py — MCP Server

Built on FastMCP from the MCP SDK. Two transport modes: stdio (default, for local agent integration) and SSE (for remote access, configurable host/port).

**21 tools:**

| Category         | Tools                                                                      |
|------------------|----------------------------------------------------------------------------|
| Lifecycle        | dominian_init, dominian_scan                                               |
| Search/Lookup    | dominian_search, dominian_node_get                                         |
| Dependencies     | dominian_deps_direct, dominian_deps_reverse                                |
| Architecture     | dominian_arch_impact, dominian_arch_communities, dominian_arch_cross_community |
| Graph Analysis   | dominian_graph_stats, dominian_graph_hotspots, dominian_graph_cycles       |
| Refactoring      | dominian_refactor_safe, dominian_refactor_impact                           |
| File Analysis    | dominian_file_functions, dominian_file_classes                             |
| Advanced Queries | dominian_nodes_by_type, dominian_nodes_by_quality, dominian_god_nodes, dominian_orphans, dominian_surprising_connections |
| Info             | dominian_info                                                              |

**2 resources:**
- `dominian://status` — current project status (node/edge counts, quality, language distribution)
- `dominian://schema` — database schema description (tables, columns, node types, edge types)

**3 prompts:**
- `code_review(entity)` — 5-step code review workflow
- `architecture_review()` — 8-step architecture review workflow
- `refactor_plan(entity)` — 5-step refactoring plan workflow

All tools return minimal format output by default. Heavy dependencies (AdaptiveScanner, QueryEngine) are imported lazily with try/except fallbacks to None, allowing the server to start even if optional dependencies are missing. Database path and project root are configurable via `DOMINIAN_DB` and `DOMINIAN_ROOT` environment variables.

### 3. database.py — GraphDatabase

The central storage and analytics engine. A single class, `GraphDatabase`, manages all persistence and graph algorithms.

**SQLite configuration:**

```python
PRAGMA journal_mode=WAL          # Write-Ahead Logging for concurrent reads
PRAGMA synchronous=NORMAL        # Balanced durability/performance
PRAGMA cache_size=-128000        # 128MB page cache (negative = KiB)
PRAGMA temp_store=MEMORY         # Temp tables in RAM
PRAGMA mmap_size=268435456       # 256MB memory-mapped I/O
```

**Thread safety:** Each thread gets its own connection via `threading.local()`. The `_lock` threading.Lock serializes schema initialization. Connections use `check_same_thread=False` and `isolation_level=None` (autocommit, with explicit `BEGIN`/`COMMIT` blocks where needed).

**Schema — 6 tables:**

```
nodes:
  id (PK)  name  type  file  language  line_start  line_end
  complexity  quality  signature  docstring  metadata (JSON)
  confidence  provenance  community  created_at  updated_at

edges:
  id (PK)  from_node (FK)  to_node (FK)  relationship  weight
  confidence  provenance  metadata (JSON)  created_at

agent_sessions:
  id (PK)  agent_type  started_at  last_active  query_count  metadata (JSON)

query_log:
  id (PK)  session_id  raw_query  resolved  result_count  latency_ms  timestamp

scan_history:
  id (PK)  root_path  file_count  node_count  edge_count  duration_s  scanned_at

file_hashes:
  file_path (PK)  content_hash  parsed_at
```

**13 indexes** on nodes (name, type, file, language, quality, complexity, confidence, community, composite type+complexity and quality+type) and 8 indexes on edges (from, to, relationship, weight, from+to pair, from+relationship, to+relationship) plus 2 on query_log.

**Batch operations:** `upsert_nodes_batch()` and `upsert_edges_batch()` use `executemany()` with `ON CONFLICT(id) DO UPDATE`, giving 10-50x throughput over individual inserts by amortizing transaction overhead.

**Automatic migration:** `_migrate()` checks `PRAGMA table_info()` for missing columns (`confidence`, `provenance`) and adds them with `ALTER TABLE`, wrapped in try/except to handle columns that already exist.

**Content-hash caching:** `is_file_changed()` computes SHA-256 of file contents and compares against `file_hashes` table. `record_file_hash()` stores the hash with `ON CONFLICT DO UPDATE`.

**Module-level import fallback:** `get_dependencies()` first queries the entity's own import/depends edges. If none exist, it looks up the module node for the same file and returns that module's import edges. This bridges the gap between Python's module-level imports and class-level dependency queries.

**Graph analytics methods:**
- `find_cycles()` — DFS with recursion stack, canonical cycle deduplication
- `get_impact(name, depth, min_weight)` — BFS traversal of reverse dependency graph
- `get_hotspots(limit)` — composite score: `complexity*3 + degree + (100-quality)/10`
- `find_god_nodes(limit)` — nodes with highest total degree (excludes dependency/module types)
- `find_surprising_connections()` — cross-top-level-directory edges excluding imports/defines
- `get_orphans()` — nodes with zero edges in either direction

### 4. formatter.py — Output Formatting

Three mutually exclusive output formats controlled by the `--format` flag:

**minimal** — The default and primary format for agent consumption. Design principles:
- Zero decorative tokens (no headers, no verbose labels)
- `folder/file:name:line(type)` as the universal locator syntax
- Every character earns its place — no padding, no alignment
- ~85% token reduction versus agent format with 100% information retention
- Semantic Unicode markers for quick visual parsing: 📥📤⚠️✅🚫📍🔍🔥🔄📦🔗📄

Example outputs:
```
📍 database.py:GraphDatabase:115(cls) c:12 q:85.3 deps:8 used_by:14
📥 GraphDatabase→ format_minimal:378(fn) imports | _node_ref:58(fn) calls
⚠️ HIGH 7:engine.py:QueryEngine,formatter.py:format_minimal,...
🚫 GraphDatabase 3direct 5total scanner.py:AdaptiveScanner,...
✅ SAFE my_utility
🔥 database.py:GraphDatabase:115(cls) c:12 q:85 | engine.py:QueryEngine:10(cls) c:8 q:72
```

**agent** — Verbose human-readable format with section headers (`===`), labeled fields, and full sentences. Used with `--format agent` for human review.

**json** — Machine-parseable format wrapped in `{"type": "agentgraph_result", "data": ...}`. Used with `--format json` for programmatic consumption.

Type abbreviations used in minimal format: `fn` (function/method), `cls` (class), `mod` (module), `var` (variable), `imp` (import), `dep` (dependency).

The `_node_ref()` function produces the universal locator: `folder/file:name:line(type)`. The `_relpath()` function converts absolute paths to the last two path components (e.g., `/home/user/project/src/main.py` → `src/main.py`).

### 5. engine.py — QueryEngine

Takes raw query strings, detects intent, resolves against the database, and returns structured results. Used as an alternative entry point to the direct command-function path.

**Intent detection** (`_detect_intent()`) maps natural language patterns to intents:
- "what does X depend on" → `dependencies`
- "what depends on X" → `dependents`
- "impact of X" → `impact`
- "safe to refactor X" → `refactoring_safety`
- "hotspots" → `hotspots`
- "cycles" / "circular" → `cycles`
- "communities" → `communities`
- "stats" → `stats`
- Fallback: `node_lookup`

**Resolution** (`_resolve()`) dispatches via a dict of 25+ resolver methods. Core resolvers are implemented; extended resolvers (architecture_patterns, layer_boundaries, coupling_analysis, etc.) return empty placeholder results for future implementation.

Each query is logged with the raw query string, resolved intent, result count, and latency in milliseconds via `db.log_query()`.

### 6. \_\_init\_\_.py — ParserRegistry, CodebaseScanner, GlobalConfig

**ParserRegistry** — Class-level registry mapping file extensions to parser classes. Two registration paths:
1. Manual: `register()` called with a parser class that declares `EXTENSIONS` and `LANGUAGE`
2. Auto-detection: `_init_ts_registry()` probes for installed tree-sitter language modules and registers them

`init_all()` must be called once at startup. It registers the six regex-based parsers (Python, JavaScript, Java, Go, Rust, C++) and then attempts tree-sitter auto-registration.

**CodebaseScanner** — Walks the file tree using `os.walk()`, filtering directories against `IGNORE_DIRS` and hidden directories (starting with `.`), dispatches each file to the appropriate parser via `ParserRegistry.get_parser()`, and batch-inserts results.

File collection respects `IGNORE_DIRS`:
```
node_modules, vendor, dist, build, target,
.git, .svn, .hg, __pycache__, .mypy_cache,
.pytest_cache, .tox, htmlcov, venv, .venv,
site-packages, .egg-info, egg-info
```

Scan flow per file:
1. Check content-hash cache → skip if unchanged
2. Get parser from registry (tree-sitter or regex fallback)
3. Call `parser.parse(file_path, root_path=...)`
4. Record file hash in database

**GlobalConfig** — Module-level defaults: `SCAN_CACHE=True`, `STREAM_OUTPUT=False`, `SAVE_DB=True`, `WATCH_LIVE=False`, `WATCH_DELAY=5.0`.

### 7. adaptive_scanner.py — AdaptiveScanner

Wraps CodebaseScanner with strategy selection based on project size:

| File count | Strategy           | Implementation          | Rationale                                     |
|------------|--------------------|-------------------------|-----------------------------------------------|
| <50        | Sequential         | Simple for-loop         | No parallelism overhead for small projects    |
| 50-500     | Threaded           | ThreadPoolExecutor      | I/O-bound parsing benefits from threading     |
| 500+       | Process            | ProcessPoolExecutor     | Bypasses GIL for CPU-bound AST parsing        |

The mode can be forced with the `mode` parameter (`"auto"`, `"sequential"`, `"threaded"`, `"process"`).

All three strategies follow the same pipeline:
1. Pre-filter: skip files whose content hash hasn't changed
2. Clear old data for changed files (`db.clear_file()`)
3. Parse each file
4. Cleanup: remove database entries for files that no longer exist on disk (`_cleanup_missing_files()`)
5. Batch-insert all new nodes and edges

Process pool uses the `spawn` start method to avoid GIL contention. The module-level `_parse_one()` function serves as the picklable entry point for ProcessPoolExecutor — it independently imports ParserRegistry and creates a fresh parser instance per worker.

### 8. tree_sitter_parser.py — TreeSitterParser, TreeSitterRegistry

**TreeSitterParser** — Wraps tree-sitter for deterministic AST-based parsing. Two-phase operation:

1. **Structural pass** — `ASTWalker.walk(root)` extracts function/class/module/import nodes and their `defines` edges
2. **Call-graph pass** — `extract_call_edges()` runs S-expression queries against the AST to find function calls, producing `calls` edges

Lazy initialization: the tree-sitter Language object and Parser are created on first `parse()` call, not at construction time. This avoids import errors at startup when tree-sitter is not installed.

**TreeSitterRegistry** — Iterates all LanguageConfig objects, creates a TreeSitterParser for each, and stores them in a dict keyed by language name. Used by ParserRegistry's `_init_ts_registry()` to register tree-sitter parsers alongside regex parsers.

**Version detection** — `_detect_ts_version()` determines the installed tree-sitter version at runtime:
- 0.22+: `Language(mod.language())` or `Language(mod.language)` (attribute-based)
- 0.20.x: `Language(mod.language, name)` (positional arguments)

Parser construction also adapts: 0.22+ uses `Parser(language)`, 0.20.x uses `Parser()` then `parser.set_language(language)`.

### 9. tree_sitter_configs.py — LanguageConfig

A dataclass that encapsulates all tree-sitter configuration for one language:

| Field                    | Purpose                                                       |
|--------------------------|---------------------------------------------------------------|
| `name`                   | Canonical language name (e.g., "python")                      |
| `module`                 | Python import path (e.g., "tree_sitter_python")               |
| `extensions`             | File suffixes (e.g., {".py", ".pyw", ".pyi"})                 |
| `node_type_map`          | AST node type → Dominian node type (e.g., "class_definition" → "class") |
| `name_fields`            | AST node type → field holding the symbol name                  |
| `body_fields`            | AST node type → field holding the body block                   |
| `param_fields`           | AST node type → field holding parameters                       |
| `return_fields`          | AST node type → field holding return type annotation           |
| `doc_node_types`         | AST node types that contain docstrings/comments                |
| `call_queries`           | S-expression patterns for call-graph extraction (second pass)  |
| `import_node_types`      | AST node types that represent imports                          |
| `inheritance_node_types` | AST node types → relationship label for inheritance            |
| `edge_weights`           | Default weights per relationship type                          |

**7 language configs:** Python, JavaScript, TypeScript, Java, Go, Rust, C/C++.

The `EXT_TO_CONFIG` dict provides extension-based lookup. `ALL_CONFIGS` is the ordered list used by TreeSitterRegistry.

### 10. import_resolver.py — Import Resolution

Maps import strings from parsed source code to actual file paths on disk. Each language has its own resolver with language-specific resolution strategies:

**Python** (`resolve_python_import`):
- Relative imports: dot-counting for parent traversal, then `.py` file or `__init__.py` package
- Absolute imports: try current directory, then project root, then `src/` prefix

**JavaScript/TypeScript** (`resolve_js_import`):
- Relative imports (starting with `.`): try exact path, then add extensions (`.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`), then `index.<ext>` in directory

**Java** (`resolve_java_import`):
- Convert dotted package name to path, check project root and `src/main/java/` convention

**Go** (`resolve_go_import`):
- Relative imports only, resolves to directories containing `.go` files

**Rust** (`resolve_rust_use`):
- `crate::` prefix → resolve from `src/` directory, try `.rs` file and `mod.rs`
- `self::`/`super::` → resolve relative to current file

**C/C++** (`resolve_cpp_include`):
- Skip system includes (angle brackets)
- Try relative to current file, then `include/`, `inc/`, `src/` directories

The dispatcher `resolve_import_to_file()` takes an import string, current file path, language, and project root, and returns an absolute file path or None.


## Key Design Decisions

### D1: SQLite over Neo4j/ArangoDB

Dominian stores its graph in SQLite, not a dedicated graph database. The reasons:

1. **Zero setup** — No server process to install, configure, or maintain. The database is a single file.
2. **Embedded** — No network layer. Queries execute in the same process as the application.
3. **WAL for concurrency** — Write-Ahead Logging allows concurrent reads while a write is in progress. This is sufficient for Dominian's read-heavy, single-writer workload.
4. **128MB cache** — SQLite's page cache, set to 128MB, holds millions of nodes in memory. Code intelligence graphs rarely exceed this.
5. **Adequate query model** — Dominian's queries are bounded-depth traversals (BFS/DFS), not arbitrary-path graph queries. SQL with recursive CTEs or application-level traversal handles this well.

The trade-off: complex multi-hop path queries are slower than in a native graph database. Dominian accepts this because its typical query depth is 3-10 hops, and the constant-factor overhead of SQL is small compared to the setup cost of a graph server.

### D2: Minimal Format as Default

The `--format minimal` flag is the default output mode. This is a deliberate choice for agent consumers:

1. **Token budgets are the binding constraint** — LLM agents operate within fixed context windows. Every token spent on output formatting is a token not available for reasoning.
2. **~85% token reduction** — Measured against the agent (verbose) format. A 200-token verbose output compresses to ~30 tokens in minimal format.
3. **6-7x more queries** — In the same token budget, an agent can make 6-7x more queries with minimal format. This directly translates to better code understanding.
4. **100% information retention** — No data is dropped. Only decorative tokens (headers, labels, alignment whitespace, full words where abbreviations suffice) are removed.

The cost: minimal format is harder for humans to read. This is acceptable because humans can use `--format agent`.

### D3: Module-Level Import Fallback

When `get_dependencies("MyClass")` is called, the method first checks for import/depends edges on the class node itself. If none exist (which is the common case in Python), it falls back to the module node for the same file and returns that module's imports.

This exists because Python's import statements are module-level, not class-level. When a file `models.py` contains `import sqlalchemy`, the import edge is on the `models` module node, not on the `User` class node defined in the same file. Without the fallback, querying "what does User depend on?" would return nothing, even though the class clearly depends on sqlalchemy.

The fallback is not applied for `get_dependents()` — only for `get_dependencies()`. This is intentional: dependents are callers/users of the entity, and those edges are correctly attached to the entity node itself.

### D4: Batch Operations for Database Writes

Individual INSERT statements in SQLite are slow because each one implicitly starts and commits a transaction (unless explicitly wrapped). The batch methods `upsert_nodes_batch()` and `upsert_edges_batch()` use `executemany()` which performs all inserts within a single implicit transaction.

Measured speedup: 10-50x on large scans (1000+ files). The exact factor depends on the number of rows per file and the underlying filesystem.

The `ON CONFLICT(id) DO UPDATE` clause makes both individual and batch upserts idempotent — re-scanning the same file updates existing records rather than creating duplicates.

Edge batch inserts temporarily disable foreign key checks (`PRAGMA foreign_keys=OFF`) because edges may reference nodes in other files that haven't been inserted yet. FK checks are re-enabled in a `finally` block.

### D5: Adaptive Scanning Strategy

The three-tier strategy is based on empirical profiling:

- **<50 files**: The overhead of creating a thread/process pool exceeds the time saved by parallelism. Sequential scanning is fastest.
- **50-500 files**: Parsing is I/O-bound (reading files from disk) and partially CPU-bound (AST construction). Threading provides 2-4x speedup without the serialization overhead of multiprocessing.
- **500+ files**: The Python GIL becomes the bottleneck. Thread-based parsing degrades because only one thread can execute Python bytecode at a time. Process-based parallelism bypasses the GIL entirely, with each worker parsing in its own interpreter.

The `spawn` start method for ProcessPoolExecutor is used instead of `fork` because:
1. Fork can cause deadlocks with SQLite connections inherited across processes
2. Fork copies the entire parent process memory, which is wasteful for workers that only need the parser code
3. Spawn creates a clean process with no inherited state

### D6: "defines" Edge Filtering

`defines` edges represent parent-child containment: a class defines its methods, a module defines its top-level functions. When asking "who depends on this function?", the parent class should not appear as a dependent — it is the container, not a user.

This filtering is applied in three places:
1. `cmd_deps_reverse()` in main_new.py
2. `dominian_deps_reverse()` in server.py
3. `cmd_refactor_safe()` in main_new.py
4. `dominian_refactor_safe()` in server.py

Without this filter, refactoring safety checks would incorrectly report a method's containing class as a dependent, making the method appear unsafe to refactor when it's actually only used by external callers.

### D7: Content-Hash Caching

On each scan, the SHA-256 hash of every file is computed and stored in the `file_hashes` table. On re-scan, `is_file_changed()` compares the current hash against the stored hash. Unchanged files are skipped entirely — no parsing, no database writes.

This makes incremental scans near-instant for projects where most files haven't changed. A 1000-file project where 5 files changed re-scans in the time it takes to parse 5 files, not 1000.

Hash computation reads files in 4KB chunks (`iter(lambda: f.read(4096), b"")`), keeping memory usage constant regardless of file size.

### D8: Dual Tree-Sitter API Support

tree-sitter 0.22 introduced a breaking change to the Language API:

| Version | Language Construction      | Parser Construction               |
|---------|---------------------------|-----------------------------------|
| 0.20.x  | `Language(mod.language, name)` | `Parser(); parser.set_language(lang)` |
| 0.22+   | `Language(mod.language())` or `Language(mod.language)` | `Parser(lang)` |

Supporting both versions prevents dependency conflicts. A project that pins tree-sitter to 0.20.x for compatibility with other tools can still use Dominian without modification.

Version detection is done once at module load time via `_detect_ts_version()` and cached in a module-level variable. The `>= (0, 22)` comparison handles any 0.22.x or later version.

### D9: Edge Weight Design

Edge weights encode the semantic strength of relationships. Higher weights mean stronger coupling:

| Relationship | Weight | Rationale                                                       |
|-------------|--------|-----------------------------------------------------------------|
| inherits    | 9.0    | Strongest coupling: subclass depends on parent's entire API     |
| defines     | 8.0    | Structural containment: class owns its methods                  |
| implements  | 8.0-9.0| Near-inheritance coupling: must satisfy interface contract      |
| calls       | 6.0    | Usage dependency: function A calls function B                   |
| imports     | 5.0-6.0| Weakest: import may be unused; merely makes names available     |

**Why inheritance is strongest:** A subclass is semantically bound to its parent. Changing the parent's API almost certainly breaks the subclass. This is the tightest form of coupling in object-oriented code.

**Why imports are weakest:** An import statement makes a name available but doesn't guarantee usage. Many codebases have unused imports (linter warnings, legacy code). Import edges are necessary for building the graph but are weaker signals for impact analysis.

**Why calls are medium:** A call edge represents actual usage, not just availability. However, a single call site is easier to update than an inheritance relationship, so calls are weighted below defines and implements.

Weights are used in:
- `get_impact()` — can filter by `min_weight` to exclude weak edges
- `get_hotspots()` — composite score includes connection count weighted by edge strength
- Impact analysis risk level calculation

### D10: Node ID as `file::name`

Node IDs are constructed as `{file}::{name}` (with spaces replaced by underscores). This scheme has three properties:

1. **Unique** — The same function name in two different files produces two different IDs. `utils.py::helper` ≠ `services.py::helper`.
2. **Deterministic** — The ID can be reconstructed from the node's name and file without a database lookup. No UUID generation, no auto-increment counters.
3. **Human-readable** — A node ID `database.py::GraphDatabase` immediately tells you which file and which entity. UUIDs would require a database query to interpret.

Edge IDs follow the pattern `{from_id}--{relationship}--{to_id}`, which is also deterministic and unique (the same source-target-relationship triple always produces the same edge ID).

The `_get_node_id_flexible()` helper allows lookups by name alone (without file) by querying the database for the most recently updated node with that name. This supports the common case where users type `dominian node get GraphDatabase` without specifying the file.


## Data Flow

### Scan Flow

```
1. User: dominian scan ./my-project

2. AdaptiveScanner.scan("./my-project")
   ├── _collect_files(root_path)
   │   └── os.walk() with IGNORE_DIRS filter
   │       → files[] list of supported source files
   │
   ├── Auto-select mode based on len(files)
   │
   ├── For each file (strategy-dependent):
   │   ├── is_file_changed(file_path)        → SHA-256 vs file_hashes table
   │   │   └── If unchanged: skip
   │   ├── clear_file(file_path)             → DELETE old nodes/edges for this file
   │   ├── ParserRegistry.get_parser(file)   → TreeSitterParser or RegexParser
   │   └── parser.parse(file_path, root_path)
   │       ├── Pass 1: ASTWalker.walk(root)  → structural nodes + defines edges
   │       └── Pass 2: extract_call_edges()  → calls edges
   │       → returns {"nodes": [...], "edges": [...], "errors": [...]}
   │
   ├── upsert_nodes_batch(all_nodes)         → INSERT ... ON CONFLICT DO UPDATE
   ├── upsert_edges_batch(all_edges)         → INSERT ... ON CONFLICT DO UPDATE
   ├── log_scan(...)                         → INSERT INTO scan_history
   └── _cleanup_missing_files(scanned_files) → DELETE stale entries

3. Output: ✓ scan 142f 1203n 3847e 4.2s mode:threaded
```

### Query Flow

```
1. User: dominian deps direct GraphDatabase --format minimal

2. cmd_deps_direct(args)
   ├── GraphDatabase(db_path)
   ├── db.get_dependencies("GraphDatabase")
   │   ├── Look up node_id for "GraphDatabase"
   │   ├── Query edges WHERE from_node = node_id
   │   │   AND relationship IN ('imports', 'depends_on', 'uses', 'calls')
   │   ├── If results: return them
   │   └── If no results: module-level import fallback
   │       ├── Get file path for "GraphDatabase" node
   │       ├── Construct module node ID from file path
   │       └── Query edges WHERE from_node = module_id AND relationship = 'imports'
   ├── db.get_node("GraphDatabase")
   └── format_output(data, "minimal", "dependencies")
       └── format_minimal(data, "dependencies")
           └── "📥 GraphDatabase→ formatter.py:format_minimal(fn) imports | ..."

3. Output printed to stdout
```

### MCP Query Flow

```
1. Agent calls: dominian_deps_direct(entity="GraphDatabase")

2. server.py: dominian_deps_direct()
   ├── _get_db(db_path)           → GraphDatabase instance
   ├── db.get_dependencies("GraphDatabase")
   ├── db.get_node("GraphDatabase")
   ├── db.close()
   ├── Filter defines edges from dependents
   └── _minimal(data, "dependencies")
       └── Returns string to MCP client

3. Agent receives minimal-format string in tool result
```


## Database Schema Details

### Node Types

| Type       | Description                                         |
|------------|-----------------------------------------------------|
| function   | Standalone function (not inside a class)            |
| method     | Function defined inside a class                     |
| class      | Class/struct/type definition                        |
| interface  | Interface/trait definition                          |
| module     | File-level module node                              |
| variable   | Module-level variable, constant, or type alias      |
| import     | Import statement (deprecated; use dependency)       |
| dependency | Import/use declaration                              |

### Edge Types (Relationships)

| Relationship | Direction        | Meaning                                      |
|-------------|------------------|----------------------------------------------|
| defines     | parent → child   | Class contains method; module contains class  |
| imports     | importer → importee | Module imports another module              |
| calls       | caller → callee  | Function A calls function B                  |
| inherits    | subclass → parent | Class extends parent class                  |
| implements  | implementor → interface | Class implements interface            |
| depends_on  | dependent → dependency | General dependency relationship        |
| uses        | user → used      | Entity uses another entity                   |

### Confidence Levels

| Value      | Meaning                                    |
|------------|--------------------------------------------|
| EXTRACTED  | Directly extracted from source code        |
| INFERRED   | Inferred from context or heuristics        |
| ASSUMED    | Assumed based on naming conventions        |

### Provenance

| Value          | Meaning                              |
|----------------|--------------------------------------|
| regex_parser   | Extracted by regex-based parser      |
| tree_sitter    | Extracted by tree-sitter AST parser  |


## Configuration

| Variable        | Default                    | Purpose                                    |
|----------------|----------------------------|--------------------------------------------|
| DOMINIAN_DB    | `.dominian/agentgraph.db`  | SQLite database path                       |
| DOMINIAN_ROOT  | Current working directory  | Project root for MCP server                |
| DOMINIAN_SRC   | Directory of server.py     | Python path for Dominian package imports   |

CLI `--db-path` overrides `DOMINIAN_DB` on a per-command basis. MCP tools accept `db_path` as a parameter with the same override semantics.


## Supported Languages

| Language   | Extensions                   | Regex Parser | Tree-Sitter Parser |
|------------|------------------------------|:------------:|:------------------:|
| Python     | .py, .pyw, .pyi              | Yes          | Yes                |
| JavaScript | .js, .jsx, .mjs, .cjs        | Yes          | Yes                |
| TypeScript | .ts, .tsx                    | Yes          | Yes                |
| Java       | .java                        | Yes          | Yes                |
| Go         | .go                          | Yes          | Yes                |
| Rust       | .rs                          | Yes          | Yes                |
| C/C++      | .c, .h, .cpp, .hpp, .cc, .hh, .cxx, .hxx | Yes | Yes         |

Regex parsers are always available as the universal fallback. Tree-sitter parsers require the `tree_sitter` package and the corresponding language package (e.g., `tree_sitter_python`) to be installed. When both are available, tree-sitter is preferred for its deterministic, complete AST extraction.


## Dependencies

**Required:**
- Python 3.10+
- SQLite3 (stdlib)

**Optional (enhanced parsing):**
- `tree_sitter` + language-specific packages (`tree_sitter_python`, `tree_sitter_javascript`, etc.)

**Optional (community detection):**
- `networkx`
- `python-louvain`

**MCP server:**
- `mcp` (FastMCP SDK)
