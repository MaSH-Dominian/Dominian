# Dominian — API Reference

This document covers every public API surface in Dominian: the CLI, MCP tools, and the Python library.

---

## Table of Contents

- [1. CLI API](#1-cli-api)
  - [1.1 Command Syntax](#11-command-syntax)
  - [1.2 Global Options](#12-global-options)
  - [1.3 Environment Variables](#13-environment-variables)
  - [1.4 Commands](#14-commands)
- [2. MCP Tools API](#2-mcp-tools-api)
  - [2.1 Tools](#21-tools)
  - [2.2 Resources](#22-resources)
  - [2.3 Prompts](#23-prompts)
- [3. Python API](#3-python-api)
  - [3.1 GraphDatabase](#31-graphdatabase)
  - [3.2 CodebaseScanner](#32-codebasescanner)
  - [3.3 AdaptiveScanner](#33-adaptivescanner)
  - [3.4 QueryEngine](#34-queryengine)
  - [3.5 Formatter](#35-formatter)
  - [3.6 ImportResolver](#36-importresolver)
  - [3.7 TreeSitterParser](#37-treesitterparser)
  - [3.8 LanguageConfig](#38-languageconfig)

---

## 1. CLI API

### 1.1 Command Syntax

All commands follow the structure:

```
dominian <group> <action> [target] [options]
```

Groups: `init`, `scan`, `search`, `node`, `deps`, `arch`, `graph`, `refactor`, `file`, `info`

### 1.2 Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--version` | flag | — | Print version and exit |
| `--db-path PATH` | string | `.dominian/agentgraph.db` | Path to the SQLite database file |
| `--format FORMAT` | enum | `minimal` | Output format: `minimal`, `agent`, or `json` |

### 1.3 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOMINIAN_DB` | `.dominian/agentgraph.db` | Database path. Overridden by `--db-path`. |
| `DOMINIAN_ROOT` | Current working directory | Project root path used for import resolution and scan targets. |

### 1.4 Commands

---

#### `dominian init`

Initialize a Dominian project. Creates the `.dominian/` directory and the SQLite database.

```
dominian init [--db-path PATH]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |

**Output (minimal):**
```
✅ Initialized .dominian/agentgraph.db
```

**Output (json):**
```json
{"type": "agentgraph_result", "data": {"status": "initialized", "db_path": ".dominian/agentgraph.db"}}
```

---

#### `dominian scan`

Scan a codebase directory and populate the database with nodes and edges.

```
dominian scan [PATH] [--db-path PATH] [--no-watch]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `PATH` | string | No | `.` (current directory) | Root directory to scan |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--no-watch` | flag | No | Watch enabled | Disable file-watcher after initial scan |

**Output (minimal):**
```
📊 142 files | 891 nodes | 2.1k edges | 3.2s
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "file_count": 142,
    "node_count": 891,
    "edge_count": 2104,
    "duration_s": 3.2
  }
}
```

**Notes:** When `--no-watch` is omitted, Dominian starts a file watcher that re-scans changed files automatically. Use `--no-watch` in CI/CD and one-shot scripts.

---

#### `dominian search`

Search for code entities by name. Returns matching nodes ranked by relevance.

```
dominian search QUERY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `QUERY` | string | Yes | — | Search string; supports partial matches |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
🔍 3 matches
src/server.py:handle_request:42(fn) | src/api.py:handle_request:15(fn) | tests/test_req.py:handle_request:8(fn)
```

**Output (agent):**
```
SEARCH RESULTS: handle_request (3 matches)
============================================================

1. src/server.py:handle_request:42  [function]  complexity:12
2. src/api.py:handle_request:15     [function]  complexity:5
3. tests/test_req.py:handle_request:8 [function] complexity:2
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "query": "handle_request",
    "results": [
      {"name": "handle_request", "type": "function", "file": "src/server.py", "line_start": 42, "complexity": 12},
      {"name": "handle_request", "type": "function", "file": "src/api.py", "line_start": 15, "complexity": 5}
    ]
  }
}
```

---

#### `dominian node get`

Get detailed information about a specific code entity.

```
dominian node get ENTITY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ENTITY` | string | Yes | — | Entity name to look up |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
📍 src/server.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3
```

**Output (agent):**
```
NODE: handle_request
============================================================

Type: function
File: src/server.py
Lines: 42-89
Quality: 78.3
Complexity: 12
Signature: def handle_request(req: Request, db: Database) -> Response
Docstring: Process incoming HTTP request and route to appropriate handler
```

**Notes:** If multiple entities share the same name (e.g., across files), the first match is returned. Disambiguate by using the `file` parameter in the Python API.

---

#### `dominian node show`

Alias for [`dominian node get`](#dominian-node-get).

```
dominian node show ENTITY [--db-path PATH] [--format minimal|agent|json]
```

Identical parameters and behavior.

---

#### `dominian deps direct`

Show direct dependencies of an entity — the nodes it imports, calls, or uses.

```
dominian deps direct ENTITY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ENTITY` | string | Yes | — | Entity name |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
📥 handle_request→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls
```

**Output (agent):**
```
DIRECT DEPENDENCIES: handle_request
============================================================

1. src/db.py:get_conn (function)     [imports]  line 15
2. src/utils.py:validate (function)  [calls]    line 8
```

---

#### `dominian deps reverse`

Show reverse dependencies — entities that depend on the target entity.

```
dominian deps reverse ENTITY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ENTITY` | string | Yes | — | Entity name |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
📤 get_conn← src/server.py:handle_request:42(fn) imports | src/api.py:list_items:20(fn) calls
```

---

#### `dominian arch impact`

Analyze the blast radius of changing an entity. Traverses the dependency graph in reverse to find all affected nodes.

```
dominian arch impact ENTITY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ENTITY` | string | Yes | — | Entity name |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,...
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "entity": "process_payment",
    "affected_count": 7,
    "affected_nodes": ["order_service", "invoice_gen", "payment_validator", "refund_handler", "..."],
    "risk_level": "HIGH"
  }
}
```

**Risk levels:** `LOW` (0–2 affected), `MEDIUM` (3–5), `HIGH` (6+).

---

#### `dominian arch communities`

Detect code communities using the Louvain algorithm. Requires `pip install dominian[communities]`.

```
dominian arch communities [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
🏘️ 4 communities | C0:23 C1:18 C2:15 C3:9
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "communities": [
      {"id": 0, "size": 23, "top_nodes": ["server", "handle_request", "Router"]},
      {"id": 1, "size": 18, "top_nodes": ["Database", "get_conn", "query"]}
    ]
  }
}
```

---

#### `dominian arch cross-community`

Find edges that cross community boundaries — these indicate hidden coupling between otherwise separate modules.

```
dominian arch cross-community [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
🔗 3 cross-community edges
C0→C1: src/server.py:Router→src/db.py:get_conn calls
C0→C2: src/server.py:handle_request→src/utils.py:validate calls
C1→C3: src/db.py:migrate→src/config.py:load_config calls
```

---

#### `dominian graph stats`

Print overall graph statistics.

```
dominian graph stats [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
📊 891 nodes | 2104 edges | 7 types | 4.2 avg_deps | 1.8 avg_used
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "node_count": 891,
    "edge_count": 2104,
    "node_types": {"function": 523, "class": 142, "method": 98, "module": 67, "variable": 34, "import": 27},
    "avg_dependencies": 4.2,
    "avg_dependents": 1.8
  }
}
```

---

#### `dominian graph hotspots`

Find the most complex nodes in the graph, ranked by cyclomatic complexity.

```
dominian graph hotspots [--limit N] [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--limit` | integer | No | `10` | Maximum number of results |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
🔥 Top 5 hotspots
src/server.py:handle_request:42 c:28 q:45.2 | src/api.py:process_data:10 c:22 q:52.1 | ...
```

---

#### `dominian graph cycles`

Detect circular dependencies in the graph.

```
dominian graph cycles [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
🔄 2 cycles
A→B→C→A | D→E→D
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "cycles": [
      ["A", "B", "C", "A"],
      ["D", "E", "D"]
    ]
  }
}
```

---

#### `dominian graph circular`

Alias for [`dominian graph cycles`](#dominian-graph-cycles).

```
dominian graph circular [--db-path PATH] [--format minimal|agent|json]
```

Identical parameters and behavior.

---

#### `dominian refactor safe`

Check whether an entity is safe to refactor. An entity is considered safe if it has zero reverse dependents.

```
dominian refactor safe ENTITY [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ENTITY` | string | Yes | — | Entity name |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
✅ SAFE utility_function
```

or

```
❌ UNSAFE process_payment | 7 dependents
```

**Output (json):**
```json
{
  "type": "agentgraph_result",
  "data": {
    "entity": "utility_function",
    "safe": true,
    "dependent_count": 0,
    "dependents": []
  }
}
```

---

#### `dominian refactor safety`

Alias for [`dominian refactor safe`](#dominian-refactor-safe).

```
dominian refactor safety ENTITY [--db-path PATH] [--format minimal|agent|json]
```

---

#### `dominian refactor impact`

Alias for [`dominian arch impact`](#dominian-arch-impact).

```
dominian refactor impact ENTITY [--db-path PATH] [--format minimal|agent|json]
```

---

#### `dominian file functions`

List all functions defined in a specific file.

```
dominian file functions FILE [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `FILE` | string | Yes | — | File path (relative to project root) |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
src/server.py 5 functions
handle_request:42(fn) c:12 | list_items:90(fn) c:4 | get_status:120(fn) c:2 | ...
```

---

#### `dominian file classes`

List all classes defined in a specific file.

```
dominian file classes FILE [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `FILE` | string | Yes | — | File path (relative to project root) |
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
src/server.py 2 classes
Router:5(cls) c:8 | RequestHandler:45(cls) c:15 | ...
```

---

#### `dominian info`

Show project status and database statistics.

```
dominian info [--db-path PATH] [--format minimal|agent|json]
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--db-path` | string | No | `.dominian/agentgraph.db` | Custom database path |
| `--format` | enum | No | `minimal` | Output format |

**Output (minimal):**
```
📂 my-project | 142 files | 891 nodes | 2104 edges | last scan: 2025-01-15T10:30:00
```

---

## 2. MCP Tools API

The MCP (Model Context Protocol) server exposes Dominian's functionality as 21 tools, 2 resources, and 3 prompts. The server is started with `dominian-mcp` and communicates over stdio or SSE transport.

### 2.1 Tools

All MCP tools return results in the same structured format. Output is always in the minimal format by default (token-optimized for LLM consumption). Parameters are passed as a JSON object.

---

#### `dominian_init`

Initialize a Dominian project database.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Status string confirming initialization.

**Example:**
```json
// Input
{"db_path": ".dominian/agentgraph.db"}

// Output
"✅ Initialized .dominian/agentgraph.db"
```

---

#### `dominian_scan`

Scan a codebase and populate the database.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `path` | string | No | `"."` | Root directory to scan |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |
| `no_watch` | boolean | No | `true` | File watcher is always disabled in MCP mode |

**Return:** Scan summary with file, node, and edge counts plus duration.

**Example:**
```json
// Input
{"path": "/home/user/my-project"}

// Output
"📊 142 files | 891 nodes | 2.1k edges | 3.2s"
```

---

#### `dominian_search`

Search for code entities by name.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `query` | string | Yes | — | Search string; partial matches supported |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of matching entities in minimal format.

**Example:**
```json
// Input
{"query": "handle_request"}

// Output
"🔍 3 matches\nsrc/server.py:handle_request:42(fn) | src/api.py:handle_request:15(fn) | tests/test_req.py:handle_request:8(fn)"
```

---

#### `dominian_node_get`

Get detailed information about a specific entity.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name to look up |
| `file` | string | No | `null` | File path to disambiguate entities with the same name |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Entity details including type, file, line range, complexity, quality, signature, and docstring.

**Example:**
```json
// Input
{"entity": "handle_request"}

// Output
"📍 src/server.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3"
```

---

#### `dominian_deps_direct`

Show direct dependencies of an entity.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name |
| `file` | string | No | `null` | File path to disambiguate |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of dependent entities with relationship types.

**Example:**
```json
// Input
{"entity": "handle_request"}

// Output
"📥 handle_request→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls"
```

---

#### `dominian_deps_reverse`

Show reverse dependencies (entities that depend on the target).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name |
| `file` | string | No | `null` | File path to disambiguate |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of entities that depend on the target.

**Example:**
```json
// Input
{"entity": "get_conn"}

// Output
"📤 get_conn← src/server.py:handle_request:42(fn) imports | src/api.py:list_items:20(fn) calls"
```

---

#### `dominian_arch_impact`

Analyze the blast radius of changing an entity.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name |
| `file` | string | No | `null` | File path to disambiguate |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Affected count, affected node list, and risk level (`LOW`/`MEDIUM`/`HIGH`).

**Example:**
```json
// Input
{"entity": "process_payment"}

// Output
"⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,..."
```

---

#### `dominian_arch_communities`

Detect code communities using the Louvain algorithm.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of communities with sizes and representative nodes.

**Example:**
```json
// Input
{}

// Output
"🏘️ 4 communities | C0:23 C1:18 C2:15 C3:9"
```

---

#### `dominian_arch_cross_community`

Find edges that cross community boundaries.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of cross-community edges with source/target communities and relationship types.

**Example:**
```json
// Input
{}

// Output
"🔗 3 cross-community edges\nC0→C1: src/server.py:Router→src/db.py:get_conn calls\n..."
```

---

#### `dominian_graph_stats`

Print graph statistics.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Node count, edge count, type breakdown, average connectivity.

**Example:**
```json
// Input
{}

// Output
"📊 891 nodes | 2104 edges | 7 types | 4.2 avg_deps | 1.8 avg_used"
```

---

#### `dominian_graph_hotspots`

Find the most complex nodes.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | No | `10` | Maximum number of results |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Nodes ranked by cyclomatic complexity.

**Example:**
```json
// Input
{"limit": 5}

// Output
"🔥 Top 5 hotspots\nsrc/server.py:handle_request:42 c:28 q:45.2 | ..."
```

---

#### `dominian_graph_cycles`

Detect circular dependencies.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of cycles, each cycle being a list of entity names forming a loop.

**Example:**
```json
// Input
{}

// Output
"🔄 2 cycles\nA→B→C→A | D→E→D"
```

---

#### `dominian_refactor_safe`

Check whether an entity is safe to refactor (zero reverse dependents).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name |
| `file` | string | No | `null` | File path to disambiguate |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Safety boolean and dependent count.

**Example:**
```json
// Input
{"entity": "utility_function"}

// Output
"✅ SAFE utility_function"
```

---

#### `dominian_refactor_impact`

Show refactoring impact (alias for `dominian_arch_impact`).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `entity` | string | Yes | — | Entity name |
| `file` | string | No | `null` | File path to disambiguate |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Same as `dominian_arch_impact`.

---

#### `dominian_file_functions`

List functions in a file.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `file` | string | Yes | — | File path relative to project root |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of function entities with line numbers and complexity.

**Example:**
```json
// Input
{"file": "src/server.py"}

// Output
"src/server.py 5 functions\nhandle_request:42(fn) c:12 | list_items:90(fn) c:4 | ..."
```

---

#### `dominian_file_classes`

List classes in a file.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `file` | string | Yes | — | File path relative to project root |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of class entities with line numbers and complexity.

**Example:**
```json
// Input
{"file": "src/server.py"}

// Output
"src/server.py 2 classes\nRouter:5(cls) c:8 | RequestHandler:45(cls) c:15"
```

---

#### `dominian_info`

Show project status and statistics.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Project name, file count, node count, edge count, last scan timestamp.

**Example:**
```json
// Input
{}

// Output
"📂 my-project | 142 files | 891 nodes | 2104 edges | last scan: 2025-01-15T10:30:00"
```

---

#### `dominian_nodes_by_type`

Retrieve all entities of a given type.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `type` | string | Yes | — | Node type: `function`, `method`, `class`, `module`, `variable`, `import` |
| `limit` | integer | No | `null` | Maximum results (null = no limit) |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of entities matching the specified type.

**Example:**
```json
// Input
{"type": "class", "limit": 5}

// Output
"📋 5 classes\nsrc/server.py:Router:5(cls) | src/db.py:Database:10(cls) | ..."
```

---

#### `dominian_nodes_by_quality`

Retrieve entities filtered by quality score range.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `quality_type` | string | Yes | — | Quality filter: `"low"` (< 50), `"medium"` (50–75), `"high"` (> 75) |
| `limit` | integer | No | `10` | Maximum results |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Entities in the specified quality band, sorted by quality ascending.

**Example:**
```json
// Input
{"quality_type": "low", "limit": 5}

// Output
"📉 5 low-quality nodes\nsrc/server.py:handle_request:42(fn) q:28.5 | src/api.py:process_data:10(fn) q:35.1 | ..."
```

---

#### `dominian_god_nodes`

Find highly connected nodes (god objects/modules) — entities with the most dependents.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | No | `10` | Maximum results |
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** Nodes ranked by number of dependents.

**Example:**
```json
// Input
{"limit": 5}

// Output
"👑 5 god nodes\nsrc/db.py:Database:10(cls) used_by:23 | src/utils.py:validate:8(fn) used_by:18 | ..."
```

---

#### `dominian_orphans`

Find unconnected nodes — entities with no dependencies and no dependents.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of orphan nodes.

**Example:**
```json
// Input
{}

// Output
"👻 3 orphans\nsrc/legacy.py:old_handler:5(fn) | src/unused.py:dead_code:12(fn) | ..."
```

---

#### `dominian_surprising_connections`

Find unexpected cross-directory coupling — dependencies between files in different top-level directories that are not obvious from the project structure.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `db_path` | string | No | `.dominian/agentgraph.db` | Database file path |

**Return:** List of surprising connections with source/target directories and relationship types.

**Example:**
```json
// Input
{}

// Output
"😲 2 surprising connections\nsrc/→tests/: src/server.py:Router→tests/mocks.py:MockDB imports\napi/→db/: api/routes.py:handler→db/queries.py:get_user calls"
```

---

### 2.2 Resources

Resources provide read-only data accessible via URI.

#### `dominian://status`

Current project status including database path, node count, edge count, and last scan time.

**Return format:**
```json
{
  "project_root": "/home/user/my-project",
  "db_path": ".dominian/agentgraph.db",
  "node_count": 891,
  "edge_count": 2104,
  "last_scan": "2025-01-15T10:30:00",
  "languages": ["python", "javascript", "typescript"]
}
```

#### `dominian://schema`

Database schema information — table definitions, column types, and index descriptions.

**Return format:**
```json
{
  "tables": {
    "nodes": {
      "columns": [
        {"name": "id", "type": "TEXT", "pk": true},
        {"name": "name", "type": "TEXT"},
        {"name": "type", "type": "TEXT"},
        {"name": "file", "type": "TEXT"},
        {"name": "language", "type": "TEXT"},
        {"name": "line_start", "type": "INTEGER"},
        {"name": "line_end", "type": "INTEGER"},
        {"name": "complexity", "type": "INTEGER"},
        {"name": "quality", "type": "REAL"},
        {"name": "signature", "type": "TEXT"},
        {"name": "docstring", "type": "TEXT"},
        {"name": "metadata", "type": "TEXT"},
        {"name": "confidence", "type": "TEXT"},
        {"name": "provenance", "type": "TEXT"},
        {"name": "community", "type": "INTEGER"}
      ],
      "indexes": ["idx_nodes_name", "idx_nodes_type", "idx_nodes_file"]
    },
    "edges": {
      "columns": [
        {"name": "id", "type": "TEXT", "pk": true},
        {"name": "from_node", "type": "TEXT"},
        {"name": "to_node", "type": "TEXT"},
        {"name": "relationship", "type": "TEXT"},
        {"name": "weight", "type": "REAL"},
        {"name": "confidence", "type": "REAL"},
        {"name": "provenance", "type": "TEXT"}
      ],
      "indexes": ["idx_edges_from", "idx_edges_to", "idx_edges_rel"]
    }
  }
}
```

### 2.3 Prompts

Prompts are pre-built workflow templates that MCP clients can invoke.

#### `code_review(entity)`

Generate a code review prompt for a specific entity. Retrieves the entity's details, dependencies, dependents, and complexity metrics.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `entity` | string | Yes | Entity name to review |

**Return:** A structured prompt string that includes the entity's source context, dependency graph, and quality metrics, ready for an LLM to perform a code review.

**Example invocation:**
```json
{
  "prompt": "code_review",
  "arguments": {"entity": "handle_request"}
}
```

**Example output:**
```
Review the entity handle_request in src/server.py (lines 42-89).

Type: function | Complexity: 12 | Quality: 78.3
Signature: def handle_request(req: Request, db: Database) -> Response

Direct dependencies (5):
- src/db.py:get_conn [imports]
- src/utils.py:validate [calls]
- src/auth.py:check_token [calls]
- src/router.py:match_route [calls]
- src/errors.py:NotFound [imports]

Reverse dependencies (3):
- src/api.py:list_items [calls]
- src/api.py:create_item [calls]
- src/middleware.py:wrap_handler [uses]

Focus areas: high complexity (12), moderate quality score (78.3), 3 dependents.
```

---

#### `architecture_review()`

Generate a full architecture review prompt. Includes community structure, cross-community edges, hotspots, cycles, and god nodes.

**Parameters:** None.

**Return:** A structured prompt string summarizing the overall codebase architecture.

**Example invocation:**
```json
{
  "prompt": "architecture_review",
  "arguments": {}
}
```

**Example output:**
```
Architecture Review for my-project

Graph: 891 nodes, 2104 edges, 7 entity types
Communities: 4 (sizes: 23, 18, 15, 9)
Cross-community edges: 3
Hotspots (top 5): handle_request (c:28), process_data (c:22), ...
Cycles: 2
God nodes (top 5): Database (23 dependents), validate (18 dependents), ...
Orphans: 3

Focus areas: high coupling between C0↔C1, 2 circular dependencies, 3 orphan nodes.
```

---

#### `refactor_plan(entity)`

Generate a refactoring plan for a specific entity. Includes impact analysis, safety assessment, and suggested approach.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `entity` | string | Yes | Entity name to plan refactoring for |

**Return:** A structured prompt string with impact analysis and refactoring strategy.

**Example invocation:**
```json
{
  "prompt": "refactor_plan",
  "arguments": {"entity": "handle_request"}
}
```

**Example output:**
```
Refactoring Plan for handle_request (src/server.py:42-89)

Safety: ❌ UNSAFE — 3 dependents
Impact: ⚠️ MEDIUM — 3 affected nodes
Complexity: 12 (above threshold of 10)

Affected entities:
- src/api.py:list_items [calls]
- src/api.py:create_item [calls]
- src/middleware.py:wrap_handler [uses]

Recommended approach:
1. Create test coverage for all 3 dependents
2. Extract sub-functions to reduce complexity (12 → target < 10)
3. Update dependents if signature changes
4. Verify no downstream breakage with `dominian arch impact` after changes
```

---

## 3. Python API

### 3.1 GraphDatabase

**Module:** `dominian.database`

The core graph database backed by SQLite. All graph operations go through this class.

#### Constructor

```python
GraphDatabase(db_path: str = "agentgraph.db")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | str | `"agentgraph.db"` | Path to the SQLite database file. Created if it does not exist. |

**Notes:** The database is opened in WAL mode for concurrent read/write performance. All tables and indexes are created automatically on initialization.

**Example:**
```python
from dominian.database import GraphDatabase

db = GraphDatabase(".dominian/agentgraph.db")
```

---

#### `upsert_node`

Insert or update a node in the graph. If a node with the same `name` and `file` exists, it is updated.

```python
upsert_node(
    name: str,
    type: str,
    file: str,
    language: str,
    line_start: int = 0,
    line_end: int = 0,
    complexity: int = 0,
    quality: float = 100.0,
    signature: str = "",
    docstring: str = "",
    metadata: Optional[Dict] = None,
    confidence: str = "EXTRACTED",
    provenance: str = "regex_parser"
) -> str
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name (e.g., `"handle_request"`) |
| `type` | str | — | Node type: `function`, `method`, `class`, `module`, `variable`, `import` |
| `file` | str | — | Source file path relative to project root |
| `language` | str | — | Source language (e.g., `"python"`, `"javascript"`) |
| `line_start` | int | `0` | Start line number |
| `line_end` | int | `0` | End line number |
| `complexity` | int | `0` | Cyclomatic complexity score |
| `quality` | float | `100.0` | Quality score (0–100) |
| `signature` | str | `""` | Function/method signature string |
| `docstring` | str | `""` | Documentation string |
| `metadata` | dict or None | `None` | Additional key-value metadata (stored as JSON) |
| `confidence` | str | `"EXTRACTED"` | Confidence level: `"EXTRACTED"` or `"INFERRED"` |
| `provenance` | str | `"regex_parser"` | Source parser: `"regex_parser"` or `"tree_sitter"` |

**Returns:** `str` — The node ID (`{file}::{name}`).

**Example:**
```python
node_id = db.upsert_node(
    name="handle_request",
    type="function",
    file="src/server.py",
    language="python",
    line_start=42,
    line_end=89,
    complexity=12,
    quality=78.3,
    signature="def handle_request(req: Request, db: Database) -> Response",
    docstring="Process incoming HTTP request",
    provenance="tree_sitter"
)
# node_id == "src/server.py::handle_request"
```

---

#### `upsert_nodes_batch`

Insert or update multiple nodes in a single transaction.

```python
upsert_nodes_batch(nodes: List[Dict]) -> int
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nodes` | List[Dict] | — | List of node dicts. Each dict must contain the keys required by `upsert_node`. |

**Returns:** `int` — Number of nodes upserted.

**Example:**
```python
count = db.upsert_nodes_batch([
    {"name": "fn_a", "type": "function", "file": "a.py", "language": "python"},
    {"name": "fn_b", "type": "function", "file": "b.py", "language": "python"},
])
# count == 2
```

---

#### `upsert_edge`

Insert or update a single edge between two nodes.

```python
upsert_edge(
    from_name: str,
    from_file: str,
    to_name: str,
    to_file: str,
    relationship: str,
    weight: float = 1.0,
    metadata: Optional[Dict] = None,
    confidence: float = 1.0,
    provenance: str = "regex_parser"
) -> str
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from_name` | str | — | Source entity name |
| `from_file` | str | — | Source entity file |
| `to_name` | str | — | Target entity name |
| `to_file` | str | — | Target entity file |
| `relationship` | str | — | Edge type: `imports`, `depends_on`, `uses`, `calls`, `defines`, `inherits`, `implements` |
| `weight` | float | `1.0` | Edge weight (1.0–9.0) |
| `metadata` | dict or None | `None` | Additional metadata (stored as JSON) |
| `confidence` | float | `1.0` | Extraction confidence (0.0–1.0) |
| `provenance` | str | `"regex_parser"` | Source parser |

**Returns:** `str` — The edge ID (`{from_id}--{relationship}--{to_id}`).

**Example:**
```python
edge_id = db.upsert_edge(
    from_name="handle_request",
    from_file="src/server.py",
    to_name="get_conn",
    to_file="src/db.py",
    relationship="imports",
    weight=3.0
)
```

---

#### `upsert_edges_batch`

Insert or update multiple edges in a single transaction.

```python
upsert_edges_batch(edges: List[Dict]) -> int
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `edges` | List[Dict] | — | List of edge dicts. Each dict must contain: `from_name`, `from_file`, `to_name`, `to_file`, `relationship`. Optional: `weight`, `metadata`, `confidence`, `provenance`. |

**Returns:** `int` — Number of edges upserted.

---

#### `get_node`

Retrieve a single node by name, optionally disambiguated by file.

```python
get_node(name: str, file: Optional[str] = None) -> Optional[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str or None | `None` | File path to disambiguate. If None, returns the first match. |

**Returns:** `Optional[Dict]` — Node dict with all columns, or `None` if not found.

**Example:**
```python
node = db.get_node("handle_request")
# {"id": "src/server.py::handle_request", "name": "handle_request", "type": "function",
#  "file": "src/server.py", "language": "python", "line_start": 42, "line_end": 89,
#  "complexity": 12, "quality": 78.3, "signature": "def handle_request(...)", ...}

node = db.get_node("handle_request", file="src/api.py")
# Returns the api.py variant, or None
```

---

#### `get_nodes_by_type`

Retrieve all nodes of a given type.

```python
get_nodes_by_type(type: str, limit: Optional[int] = None) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | str | — | Node type: `function`, `method`, `class`, `module`, `variable`, `import` |
| `limit` | int or None | `None` | Maximum results. None returns all. |

**Returns:** `List[Dict]` — List of node dicts.

---

#### `get_nodes_by_file`

Retrieve all nodes defined in a specific file.

```python
get_nodes_by_file(file: str) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | str | — | File path relative to project root |

**Returns:** `List[Dict]` — List of node dicts in the file.

---

#### `get_nodes_by_name`

Retrieve nodes matching a name (may return multiple if entities share a name across files).

```python
get_nodes_by_name(name: str, limit: Optional[int] = None) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `limit` | int or None | `None` | Maximum results |

**Returns:** `List[Dict]` — List of matching node dicts.

---

#### `get_nodes_by_quality`

Retrieve nodes filtered by quality score range.

```python
get_nodes_by_quality(quality_type: str, limit: int = 10) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `quality_type` | str | — | `"low"` (quality < 50), `"medium"` (50 ≤ quality ≤ 75), `"high"` (quality > 75) |
| `limit` | int | `10` | Maximum results |

**Returns:** `List[Dict]` — Nodes in the specified quality band, sorted by quality ascending.

---

#### `search_nodes`

Fuzzy-search for nodes by name.

```python
search_nodes(query: str, limit: int = 20) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | — | Search string; supports partial and case-insensitive matching |
| `limit` | int | `20` | Maximum results |

**Returns:** `List[Dict]` — Matching nodes ranked by relevance.

---

#### `get_dependencies`

Get direct dependencies of an entity — the nodes it imports, calls, or uses.

```python
get_dependencies(name: str, file: Optional[str] = None) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str or None | `None` | File path to disambiguate |

**Returns:** `List[Dict]` — List of dependency edge records with `to_node` information.

**Important note — module-level import fallback:** If no direct edges are found from the entity, `get_dependencies` falls back to returning module-level import nodes in the same file. This handles cases where a function uses an import but no explicit `calls` or `uses` edge was extracted. The fallback returns `import`-type nodes from the same file as the target entity.

**Example:**
```python
deps = db.get_dependencies("handle_request")
# [{"name": "get_conn", "file": "src/db.py", "relationship": "imports", ...},
#  {"name": "validate", "file": "src/utils.py", "relationship": "calls", ...}]
```

---

#### `get_dependents`

Get reverse dependencies — entities that depend on the target entity.

```python
get_dependents(name: str, file: Optional[str] = None) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str or None | `None` | File path to disambiguate |

**Returns:** `List[Dict]` — List of dependent edge records with `from_node` information.

---

#### `get_impact`

Analyze the blast radius of changing an entity. Performs a breadth-first traversal of reverse dependencies up to the specified depth.

```python
get_impact(
    name: str,
    file: Optional[str] = None,
    depth: int = 3,
    min_weight: float = 0.0
) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str or None | `None` | File path to disambiguate |
| `depth` | int | `3` | Maximum traversal depth |
| `min_weight` | float | `0.0` | Minimum edge weight to follow (filters weak edges) |

**Returns:** `Dict` with keys:
- `affected_count` (int) — Total number of affected entities
- `affected_nodes` (List[str]) — Names of affected entities
- `risk_level` (str) — `"LOW"` (0–2), `"MEDIUM"` (3–5), or `"HIGH"` (6+)

**Example:**
```python
impact = db.get_impact("process_payment", depth=3)
# {"affected_count": 7, "affected_nodes": ["order_service", "invoice_gen", ...], "risk_level": "HIGH"}
```

---

#### `get_hotspots`

Find the most complex nodes in the graph.

```python
get_hotspots(limit: int = 10) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | `10` | Maximum results |

**Returns:** `List[Dict]` — Nodes sorted by complexity descending.

---

#### `get_stats`

Get overall graph statistics.

```python
get_stats() -> Dict
```

**Returns:** `Dict` with keys:
- `node_count` (int)
- `edge_count` (int)
- `node_types` (Dict[str, int]) — Count of each node type
- `avg_dependencies` (float) — Average outgoing edges per node
- `avg_dependents` (float) — Average incoming edges per node

---

#### `get_communities`

Detect code communities using the Louvain algorithm.

```python
get_communities() -> List[Dict]
```

**Returns:** `List[Dict]` — Each dict has keys:
- `id` (int) — Community ID
- `size` (int) — Number of nodes in the community
- `top_nodes` (List[str]) — Representative node names

**Notes:** Requires `python-louvain` and `networkx` (install with `pip install dominian[communities]`). Raises an import error if not available.

---

#### `find_cycles`

Detect circular dependencies.

```python
find_cycles() -> List[List[str]]
```

**Returns:** `List[List[str]]` — Each inner list is a cycle represented as a sequence of node names forming a loop (first and last element are the same).

**Example:**
```python
cycles = db.find_cycles()
# [["A", "B", "C", "A"], ["D", "E", "D"]]
```

---

#### `find_god_nodes`

Find highly connected nodes (god objects).

```python
find_god_nodes(limit: int = 10) -> List[Dict]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | `10` | Maximum results |

**Returns:** `List[Dict]` — Nodes sorted by number of dependents descending. Each dict includes a `dependent_count` key.

---

#### `find_surprising_connections`

Find unexpected cross-directory coupling.

```python
find_surprising_connections() -> List[Dict]
```

**Returns:** `List[Dict]` — Each dict has keys:
- `from_name`, `from_file`, `from_dir`
- `to_name`, `to_file`, `to_dir`
- `relationship` (str)

---

#### `get_orphans`

Find unconnected nodes (no dependencies and no dependents).

```python
get_orphans() -> List[Dict]
```

**Returns:** `List[Dict]` — Orphan node records.

---

#### `delete_node`

Delete a node and all its associated edges.

```python
delete_node(name: str, file: str) -> bool
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str | — | File path (required for disambiguation) |

**Returns:** `bool` — `True` if a node was deleted, `False` if not found.

---

#### `rename_node`

Rename a node and update all associated edges.

```python
rename_node(old_name: str, new_name: str, file: str) -> bool
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `old_name` | str | — | Current entity name |
| `new_name` | str | — | New entity name |
| `file` | str | — | File path (required for disambiguation) |

**Returns:** `bool` — `True` if renamed, `False` if not found.

---

#### `update_node_metrics`

Update complexity and/or quality score for a node.

```python
update_node_metrics(
    name: str,
    file: str,
    complexity: Optional[int] = None,
    quality: Optional[float] = None
) -> bool
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | — | Entity name |
| `file` | str | — | File path |
| `complexity` | int or None | `None` | New complexity score. None = no change. |
| `quality` | float or None | `None` | New quality score. None = no change. |

**Returns:** `bool` — `True` if updated, `False` if not found.

---

#### `delete_edge`

Delete a specific edge.

```python
delete_edge(
    from_name: str,
    from_file: str,
    to_name: str,
    to_file: str,
    relationship: Optional[str] = None
) -> bool
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `from_name` | str | — | Source entity name |
| `from_file` | str | — | Source entity file |
| `to_name` | str | — | Target entity name |
| `to_file` | str | — | Target entity file |
| `relationship` | str or None | `None` | If specified, only delete edges of this relationship type. If None, delete all edges between the two nodes. |

**Returns:** `bool` — `True` if an edge was deleted.

---

#### `clear_file`

Delete all nodes and edges associated with a specific file.

```python
clear_file(file: str) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | str | — | File path to clear |

**Returns:** None.

---

#### `clear_all`

Delete all nodes and edges from the database. Does not drop the tables.

```python
clear_all() -> None
```

**Returns:** None.

---

#### `log_scan`

Record a scan operation in the audit log.

```python
log_scan(
    root_path: str,
    file_count: int,
    node_count: int,
    edge_count: int,
    duration_s: float
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root_path` | str | — | Scanned root directory |
| `file_count` | int | — | Number of files scanned |
| `node_count` | int | — | Number of nodes extracted |
| `edge_count` | int | — | Number of edges extracted |
| `duration_s` | float | — | Scan duration in seconds |

---

#### `log_query`

Record a query operation in the audit log.

```python
log_query(
    session_id: str,
    raw_query: str,
    resolved: str,
    result_count: int,
    latency_ms: float
) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | str | — | Session identifier |
| `raw_query` | str | — | Original query string |
| `resolved` | str | — | Resolved entity name |
| `result_count` | int | — | Number of results returned |
| `latency_ms` | float | — | Query latency in milliseconds |

---

#### `close`

Close the database connection.

```python
close() -> None
```

**Returns:** None.

**Example:**
```python
db.close()
```

---

### 3.2 CodebaseScanner

**Module:** `dominian` (`__init__.py`)

Regex-based codebase scanner. Uses the `ParserRegistry` to dispatch to language-specific regex parsers.

#### Constructor

```python
CodebaseScanner(db: Optional[GraphDatabase] = None, root: Optional[str] = None, config: Optional[GlobalConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | GraphDatabase or None | `None` | Database instance. If None, creates one at the default path. |
| `root` | str or None | `None` | Project root directory. Defaults to `DOMINIAN_ROOT` or cwd. |
| `config` | GlobalConfig or None | `None` | Configuration. If None, uses defaults. |

---

#### `scan`

Scan an entire directory tree.

```python
scan(root: Optional[str] = None) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root` | str or None | `None` | Root directory. Falls back to constructor `root`, then `DOMINIAN_ROOT`, then cwd. |

**Returns:** `Dict` with keys:
- `file_count` (int)
- `node_count` (int)
- `edge_count` (int)
- `duration_s` (float)

---

#### `scan_file`

Scan a single file.

```python
scan_file(file_path: str) -> Tuple
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the source file |

**Returns:** `Tuple` — `(nodes: List[Dict], edges: List[Dict])`

---

#### `on_file_change`

Handle a file change event (for live watching). Re-scans the file and updates the database.

```python
on_file_change(file_path: str) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the changed file |

---

#### ParserRegistry (inner class)

Manages language-specific regex parsers.

```python
class ParserRegistry:
    def register(extension: str, parser) -> None          # Register a parser for a file extension
    def get_parser(extension: str) -> Optional[Parser]    # Get parser for extension
    def supported_extensions() -> List[str]               # List all registered extensions
    def is_supported(extension: str) -> bool              # Check if extension has a parser
    def init_all() -> None                                # Initialize all built-in parsers
```

---

#### GlobalConfig (inner class)

Scanner configuration dataclass.

```python
class GlobalConfig:
    SCAN_CACHE: bool = True       # Cache scan results
    STREAM_OUTPUT: bool = False   # Stream results as they are found
    SAVE_DB: bool = True          # Persist results to database
    WATCH_LIVE: bool = False      # Enable live file watching
```

---

### 3.3 AdaptiveScanner

**Module:** `dominian.adaptive_scanner`

Enhanced scanner that uses both regex and tree-sitter parsers, with adaptive selection and parallel processing.

#### Constructor

```python
AdaptiveScanner(db: Optional[GraphDatabase] = None, root: Optional[str] = None, config: Optional[GlobalConfig] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | GraphDatabase or None | `None` | Database instance. If None, creates one at the default path. |
| `root` | str or None | `None` | Project root directory. |
| `config` | GlobalConfig or None | `None` | Configuration. |

---

#### `scan`

Scan an entire directory tree with adaptive parser selection and optional parallel processing.

```python
scan(
    root: Optional[str] = None,
    mode: str = "auto",
    workers: int = 4,
    stream_results: bool = False
) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `root` | str or None | `None` | Root directory. Falls back to constructor `root`, then cwd. |
| `mode` | str | `"auto"` | Parser selection mode: `"auto"` (use tree-sitter if available, regex fallback), `"regex"` (force regex), `"tree_sitter"` (force tree-sitter, error if unavailable) |
| `workers` | int | `4` | Number of parallel workers for file scanning |
| `stream_results` | bool | `False` | Stream results to the database as they are found instead of batching |

**Returns:** `Dict` with keys:
- `file_count` (int)
- `node_count` (int)
- `edge_count` (int)
- `duration_s` (float)
- `parser_used` (Dict[str, str]) — Map of file extension to parser type used

---

#### `scan_file`

Scan a single file with adaptive parser selection.

```python
scan_file(file_path: str) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the source file |

**Returns:** `Dict` with keys:
- `nodes` (List[Dict])
- `edges` (List[Dict])
- `parser` (str) — `"tree_sitter"` or `"regex_parser"`

---

#### `on_file_change`

Handle a file change event.

```python
on_file_change(file_path: str) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the changed file |

---

### 3.4 QueryEngine

**Module:** `dominian.engine`

Natural language query resolver. Translates raw query strings into structured database lookups.

#### Constructor

```python
QueryEngine(db: GraphDatabase)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db` | GraphDatabase | — | Database instance (required) |

---

#### `query`

Execute a query against the graph database.

```python
query(raw: str, session_id: str = "default", limit: int = 25) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `raw` | str | — | Raw query string (entity name, partial match, or natural language) |
| `session_id` | str | `"default"` | Session identifier for audit logging |
| `limit` | int | `25` | Maximum number of results |

**Returns:** `Dict` with keys:
- `query` (str) — The original raw query
- `resolved` (str) — The resolved entity name (best match)
- `results` (List[Dict]) — Matching nodes
- `result_count` (int) — Number of results
- `latency_ms` (float) — Query latency

**Example:**
```python
from dominian.engine import QueryEngine
from dominian.database import GraphDatabase

db = GraphDatabase(".dominian/agentgraph.db")
engine = QueryEngine(db)

result = engine.query("handle_request")
# {"query": "handle_request", "resolved": "handle_request",
#  "results": [...], "result_count": 3, "latency_ms": 1.2}
```

---

### 3.5 Formatter

**Module:** `dominian.formatter`

Output formatting functions for converting structured data to the three output formats.

#### `format_minimal`

Format data in the ultra-compact minimal format (~85% token reduction vs verbose).

```python
format_minimal(data: Any, command_type: str = "general") -> str
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | Any | — | Structured result data from database or engine |
| `command_type` | str | `"general"` | Command type hint for format selection: `"general"`, `"deps"`, `"impact"`, `"search"`, `"hotspots"`, `"cycles"`, `"communities"` |

**Returns:** `str` — Compact formatted string using locator syntax.

---

#### `format_for_claude`

Format data in the human-readable agent format with headers and structure.

```python
format_for_claude(data: Any, *, command_type: Optional[str] = None, focus_entity: Optional[str] = None) -> str
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | Any | — | Structured result data |
| `command_type` | str or None | `None` | Command type hint |
| `focus_entity` | str or None | `None` | Entity name to highlight in the output |

**Returns:** `str` — Multi-line formatted string with headers and labeled fields.

---

#### `format_json`

Format data as a JSON-compatible dict.

```python
format_json(data: Any) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | Any | — | Structured result data |

**Returns:** `Dict` — JSON-serializable dict wrapped in `{"type": "agentgraph_result", "data": ...}`.

---

#### OutputFormat

Enum for output format selection.

```python
class OutputFormat(str, Enum):
    MINIMAL = "minimal"
    AGENT = "agent"
    JSON = "json"
```

---

### 3.6 ImportResolver

**Module:** `dominian.import_resolver`

Resolves import statements to actual file paths in the project.

#### `resolve_import_to_file`

Main entry point for import resolution. Dispatches to the appropriate language-specific resolver.

```python
resolve_import_to_file(
    import_str: str,
    current_file: str,
    language: str,
    project_root: str
) -> Optional[str]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `import_str` | str | — | The import path string (e.g., `"src.db"`, `"./utils"`) |
| `current_file` | str | — | The file containing the import statement |
| `language` | str | — | Source language (determines which resolver to use) |
| `project_root` | str | — | Project root directory for resolving absolute imports |

**Returns:** `Optional[str]` — Resolved file path relative to project root, or `None` if unresolvable.

**Example:**
```python
from dominian.import_resolver import resolve_import_to_file

path = resolve_import_to_file("src.db", "src/server.py", "python", "/home/user/project")
# "src/db.py"
```

---

#### Language-Specific Resolvers

Each resolver handles the import semantics of its language.

**`resolve_python_import`**
```python
resolve_python_import(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves Python imports using relative and absolute path logic. Handles `from X import Y` and `import X.Y` patterns. Looks for `.py`, `.pyw`, and `.pyi` files, plus `__init__.py` in package directories.

**`resolve_js_import`**
```python
resolve_js_import(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves JavaScript imports. Handles relative imports (`./utils`, `../lib`). Tries extensions `.js`, `.jsx`, `.mjs`, `.cjs`, and `index.js` in directories.

**`resolve_java_import`**
```python
resolve_java_import(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves Java imports using package-to-directory mapping. Converts dot-separated package names to directory paths.

**`resolve_go_import`**
```python
resolve_go_import(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves Go imports relative to the module. Handles both standard library and internal package references.

**`resolve_rust_use`**
```python
resolve_rust_use(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves Rust `use` statements relative to the crate root. Handles `crate::`, `super::`, and `self::` prefixes.

**`resolve_cpp_include`**
```python
resolve_cpp_include(import_str: str, current_file: str, project_root: str) -> Optional[str]
```
Resolves C/C++ `#include` directives. Handles both quoted includes (relative) and angle-bracket includes (searches include paths).

---

### 3.7 TreeSitterParser

**Module:** `dominian.tree_sitter_parser`

Tree-sitter-based parser for high-fidelity code extraction.

#### TreeSitterParser

```python
TreeSitterParser(config: Optional[GlobalConfig] = None, extensions: Optional[List[str]] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | GlobalConfig or None | `None` | Scanner configuration |
| `extensions` | List[str] or None | `None` | File extensions to handle. If None, handles all supported extensions. |

---

#### `parse`

Parse a single source file using tree-sitter.

```python
parse(file_path: str, root_path: Optional[str] = None) -> Dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the source file |
| `root_path` | str or None | `None` | Project root for resolving relative paths |

**Returns:** `Dict` with keys:
- `nodes` (List[Dict]) — Extracted entities
- `edges` (List[Dict]) — Extracted relationships
- `language` (str) — Detected language
- `provenance` (str) — `"tree_sitter"`

**Example:**
```python
from dominian.tree_sitter_parser import TreeSitterParser

parser = TreeSitterParser()
result = parser.parse("src/server.py", root_path="/home/user/project")
# {"nodes": [...], "edges": [...], "language": "python", "provenance": "tree_sitter"}
```

---

#### TreeSitterRegistry

Manages tree-sitter language grammars. Loads grammars lazily on first use.

```python
class TreeSitterRegistry:
    def get_language(lang: str) -> Optional[Language]    # Get tree-sitter Language object
    def get_parser(lang: str) -> Optional[Parser]        # Get tree-sitter Parser for language
    def is_available(lang: str) -> bool                  # Check if grammar is installed
    def available_languages() -> List[str]               # List languages with installed grammars
```

---

### 3.8 LanguageConfig

**Module:** `dominian.tree_sitter_configs`

Dataclass defining how tree-sitter extracts entities from a specific language.

#### Dataclass Definition

```python
@dataclass
class LanguageConfig:
    name: str                     # Language display name (e.g., "Python")
    module: str                   # Tree-sitter grammar module name (e.g., "tree_sitter_python")
    extensions: List[str]         # File extensions (e.g., [".py", ".pyw", ".pyi"])
    node_type_map: Dict[str, str] # Tree-sitter node type → Dominian node type
    name_fields: List[str]        # Fields to extract entity names from
    body_fields: List[str]        # Fields containing entity bodies (for line_end)
    param_fields: List[str]       # Fields containing parameter lists
    return_fields: List[str]      # Fields containing return type annotations
    doc_node_types: List[str]     # Node types that contain docstrings
    call_queries: List[str]       # Tree-sitter queries for call expressions
    import_node_types: List[str]  # Node types representing imports
    inheritance_node_types: List[str]  # Node types representing inheritance
    edge_weights: Dict[str, float]     # Relationship type → default weight
```

---

#### Predefined Configurations

Seven language configurations are provided:

**`PYTHON_CONFIG`**
- `name`: `"Python"`
- `module`: `"tree_sitter_python"`
- `extensions`: `[".py", ".pyw", ".pyi"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "inherits": 4.0, "defines": 1.0, "uses": 1.5}`

**`JAVASCRIPT_CONFIG`**
- `name`: `"JavaScript"`
- `module`: `"tree_sitter_javascript"`
- `extensions`: `[".js", ".jsx", ".mjs", ".cjs"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "defines": 1.0, "uses": 1.5}`

**`TYPESCRIPT_CONFIG`**
- `name`: `"TypeScript"`
- `module`: `"tree_sitter_typescript"`
- `extensions`: `[".ts", ".tsx"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "inherits": 4.0, "defines": 1.0, "uses": 1.5}`

**`JAVA_CONFIG`**
- `name`: `"Java"`
- `module`: `"tree_sitter_java"`
- `extensions`: `[".java"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "inherits": 4.0, "implements": 4.0, "defines": 1.0, "uses": 1.5}`

**`GO_CONFIG`**
- `name`: `"Go"`
- `module`: `"tree_sitter_go"`
- `extensions`: `[".go"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "defines": 1.0, "uses": 1.5}`

**`RUST_CONFIG`**
- `name`: `"Rust"`
- `module`: `"tree_sitter_rust"`
- `extensions`: `[".rs"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "inherits": 4.0, "defines": 1.0, "uses": 1.5}`

**`CPP_CONFIG`**
- `name`: `"C++"`
- `module`: `"tree_sitter_cpp"`
- `extensions`: `[".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"]`
- `edge_weights`: `{"imports": 3.0, "calls": 2.0, "inherits": 4.0, "defines": 1.0, "uses": 1.5}`

---

## Appendix: Node Types

| Type | Description |
|------|-------------|
| `function` | Standalone function |
| `method` | Class method |
| `class` | Class definition |
| `module` | Module/file-level entity |
| `variable` | Module-level variable or constant |
| `import` | Import statement |
| `dependency` | External dependency reference |

## Appendix: Edge Relationship Types

| Relationship | Direction | Weight | Description |
|-------------|-----------|--------|-------------|
| `imports` | A → B | 3.0 | A imports B |
| `calls` | A → B | 2.0 | A calls function/method B |
| `uses` | A → B | 1.5 | A uses B (reference without call) |
| `defines` | A → B | 1.0 | A defines B (e.g., class defines method) |
| `inherits` | A → B | 4.0 | A inherits from B |
| `implements` | A → B | 4.0 | A implements interface B |
| `depends_on` | A → B | 1.0 | Generic dependency (fallback) |

## Appendix: Output Format Comparison

| Aspect | `minimal` | `agent` | `json` |
|--------|-----------|---------|--------|
| Token cost | ~1x (baseline) | ~5x | ~4x |
| Machine parseable | Partial (locator syntax) | No | Yes |
| Human readable | With practice | Yes | No |
| Default for CLI | Yes | No | No |
| Default for MCP | Yes | No | No |
| Use case | LLM agents, scripts | Human review | Programmatic use |
