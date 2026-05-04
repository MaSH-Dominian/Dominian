# Changelog

All notable changes to Dominian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.7] - 2025-05-04

### Added

- **MCP Server**: Full Model Context Protocol server (`server.py`) with 21 tools, 2 resources, and 3 prompts
- **Minimal output format**: Ultra-compact output designed for LLM agent consumption with ~85% token reduction
- **Agent output format**: Structured human-readable format with section headers and context
- **JSON output format**: Machine-parseable format for programmatic use
- **Universal locator syntax**: `folder/file:name:line(type)` for compact entity references
- **Adaptive scanner**: Auto-selects scan strategy based on project size (sequential < 50 files, threaded 50-500, process 500+)
- **Content-hash caching**: Skips re-scanning unchanged files using SHA-256 hashes
- **Tree-sitter integration**: Dual API support for tree-sitter 0.20.x and 0.22.x
- **7 language configurations**: Python, JavaScript, TypeScript, Java, Go, Rust, C/C++
- **Import resolution**: Cross-file import resolution for all 7 supported languages
- **Community detection**: Louvain modularity algorithm for code community grouping
- **Cross-community edges**: Detection of architectural boundary violations
- **Impact analysis**: Transitive dependency analysis up to depth 10 with risk levels (LOW/MEDIUM/HIGH/CRITICAL)
- **Refactoring safety**: Checks if entities are safe to modify based on dependent count
- **Circular dependency detection**: DFS-based cycle detection with deduplication
- **Complexity hotspots**: Composite ranking of complexity, connections, and inverse quality
- **God node detection**: Identifies highly-connected entities that wire everything together
- **Orphan detection**: Finds entities with no connections (potential dead code)
- **Surprising connections**: Identifies cross-directory coupling between top-level folders
- **Batch database operations**: `upsert_nodes_batch()` and `upsert_edges_batch()` for 10-50x faster inserts
- **WAL mode**: SQLite Write-Ahead Logging for concurrent read/write performance
- **Full indexing**: 16 indexes on nodes table, 8 indexes on edges table
- **Database migration**: Automatic schema migration for existing databases
- **File cleanup**: Removes stale database entries for deleted files during re-scan
- **Module-level import fallback**: When a class/function has no import edges, falls back to the module's imports for the same file
- **MCP prompts**: `code_review`, `architecture_review`, and `refactor_plan` workflow templates
- **CLI aliases**: `node show` (alias for `node get`), `graph circular` (alias for `graph cycles`), `refactor safety` (alias for `refactor safe`)

### Changed

- All output formatting centralized in `formatter.py` — CLI commands no longer produce output directly
- Default output format changed to `minimal` for all commands
- Exit code 1 for empty search results (agents can distinguish success from no-results)
- `defines` edges filtered from reverse dependency queries (they are parent-child containment, not usage)

### Technical

- SQLite with WAL mode, 128MB cache, memory temp store, 256MB mmap
- Thread-safe database connections using `threading.local()`
- Lazy tree-sitter initialization (parsers loaded on first use)
- Process pool uses `spawn` method to avoid GIL contention
- Edge deduplication during scan phase

## [1.0.0] - Initial Release

### Added

- Basic CLI with init, scan, search, node, deps, and graph commands
- SQLite graph database with nodes and edges tables
- Regex-based parsers for Python and JavaScript
- QueryEngine with intent detection
- Agent-format output (verbose)
