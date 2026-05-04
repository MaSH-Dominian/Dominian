# Dominian — AI Agent Integration Guide

This document is a technical reference for integrating Dominian with LLM agents via the Model Context Protocol (MCP). It covers configuration, tool usage, output parsing, and common agent workflows.

---

## 1. Introduction

### The Problem

When an LLM agent operates on a codebase, it faces two structural limitations:

1. **Token budgets are finite.** Reading every file to understand dependencies is prohibitively expensive. A 50-file Python project may contain 15,000 lines of code, but the dependency graph that describes all cross-entity relationships fits in under 2,000 tokens.

2. **Text search cannot answer structural questions.** Grep finds where a symbol appears, but cannot answer: "What breaks if I change this function's signature?" or "Which modules have circular dependencies?" These are graph queries, not text queries.

### What Dominian Provides

Dominian builds a dependency graph of the codebase in SQLite and exposes it through 21 MCP tools. The agent queries the graph instead of reading files. A single tool call replaces reading dozens of files to trace a dependency chain.

Key properties for agent consumption:

- **Minimal output format** — ~85% token reduction versus verbose output. Every tool returns compact, symbol-dense strings by default.
- **Deterministic structure** — Output follows fixed patterns with known delimiters, making it parseable by agents without ambiguity.
- **No pagination** — Results are bounded by the tool's `limit` parameter. There is no cursor-based pagination to manage.
- **Local-first** — The SQLite database lives in the project directory. No network calls, no API keys, no rate limits.

### When to Use Dominian

| Use Case | Dominian Helps? | Why |
|----------|-----------------|-----|
| Understanding what a function depends on | Yes | `deps_direct` returns the full list in one call |
| Finding who uses a class | Yes | `deps_reverse` with "defines" edges filtered out |
| Assessing change risk before modifying code | Yes | `arch_impact` computes transitive blast radius |
| Checking if code is safe to refactor | Yes | `refactor_safe` returns SAFE or blocked with counts |
| Finding dead code | Yes | `orphans` returns unconnected entities |
| Detecting circular dependencies | Yes | `graph_cycles` runs DFS-based cycle detection |
| Understanding modular structure | Yes | `arch_communities` + `arch_cross_community` |
| Reading the full source of a function | No | Dominian is a graph query tool, not a file reader |
| Running tests | No | Dominian does not execute code |
| Fixing lint errors | No | Dominian does not analyze syntax or style |

---

## 2. Setup

### Prerequisites

```bash
pip install dominian[mcp]
```

This installs the core package plus the FastMCP dependency. The MCP server entry point is `dominian-mcp`.

Verify installation:

```bash
dominian --version

dominian-mcp --help
# usage: dominian-mcp [-h] [--transport {stdio,sse}] [--host HOST] [--port PORT] [--db-path DB_PATH]
```

### Claude Desktop Configuration

Edit `claude_desktop_config.json` (location varies by OS):

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "dominian": {
      "command": "dominian-mcp",
      "args": []
    }
  }
}
```

With a custom database path:

```json
{
  "mcpServers": {
    "dominian": {
      "command": "dominian-mcp",
      "args": ["--db-path", "/path/to/project/.dominian/agentgraph.db"]
    }
  }
}
```

### Cursor Configuration

Add to `.cursor/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "dominian": {
      "command": "dominian-mcp",
      "args": []
    }
  }
}
```

### SSE Transport (Remote / Multi-Agent)

For scenarios where the agent cannot spawn a local process (remote servers, containerized agents):

```bash
dominian-mcp --transport sse --host 0.0.0.0 --port 8080
```

Client configuration for SSE:

```json
{
  "mcpServers": {
    "dominian": {
      "url": "http://localhost:8080/sse"
    }
  }
}
```

Note: SSE transport is stateless between reconnections. The database persists on disk, but any in-process scan state is lost.

### Custom Client (Programmatic)

Using the MCP Python SDK:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="dominian-mcp",
    args=[],
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("dominian_info", {})
        print(result)
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DOMINIAN_DB` | `.dominian/agentgraph.db` | Database path when `db_path` argument is omitted |
| `DOMINIAN_ROOT` | Current working directory | Project root for scan operations |

The `db_path` argument on individual tools overrides `DOMINIAN_DB`, which overrides the default.

---

## 3. Workflow

Dominian follows a strict three-phase workflow: **init → scan → query**. The database must exist and be populated before any query tools return meaningful results.

### Phase 1: Initialize

```
dominian_init()
```

Creates the SQLite database at `.dominian/agentgraph.db` (or the specified `db_path`) with the full schema: `nodes` table, `edges` table, and all 24 indexes. If the database already exists, this is a no-op (schema migration happens automatically).

Output:
```
✓ Initialized .dominian/agentgraph.db
```

### Phase 2: Scan

```
dominian_scan(path=".")
```

Walks the directory tree, parses source files, extracts entities and edges, and writes them to the database. Content-hash caching skips files that haven't changed since the last scan.

The `mode` parameter controls parallelism:

| Mode | When to Use | Behavior |
|------|-------------|----------|
| `auto` | Default | <50 files: sequential, 50-500: threaded, 500+: process |
| `sequential` | Small projects, debugging | Single-threaded, deterministic order |
| `threaded` | Medium projects (50-500 files) | Thread pool, shared database via WAL |
| `process` | Large projects (500+ files) | Process pool with `spawn` to avoid GIL |

The `workers` parameter (default 4) controls pool size for threaded/process modes.

Output:
```
✓ Scanned 147 files: 1,243 nodes, 3,891 edges (2.1s)
```

### Phase 3: Query

Any of the 18 query tools. Examples:

```
dominian_search(query="handle_request")
dominian_deps_reverse(entity="handle_request")
dominian_arch_impact(entity="process_payment")
```

### Full Lifecycle Example

```
Step 1: dominian_init()
  → ✓ Initialized .dominian/agentgraph.db

Step 2: dominian_scan(path="/path/to/project")
  → ✓ Scanned 312 files: 2,847 nodes, 9,431 edges (4.7s)

Step 3: dominian_graph_stats()
  → ✓ 2847n 9431e q:74.2 Python

Step 4: dominian_search(query="payment")
  → 🔍 5: process_payment, validate_payment, PaymentError, PaymentGateway, payment_callback

Step 5: dominian_node_get(entity="process_payment")
  → 📍 src/payments/service.py:process_payment:88-156 fn c:18 q:65.2 deps:7 used_by:4
```

### Re-scanning

After code changes, re-run `dominian_scan`. Content-hash caching means only changed files are re-parsed. Deleted files have their stale entries cleaned up automatically.

```
dominian_scan(path=".")
  → ✓ Scanned 147 files: 1,251 nodes, 3,912 edges (0.4s)
```

The 0.4s versus the initial 2.1s reflects caching — only 3 of 147 files changed.

---

## 4. Tool Reference

All 21 MCP tools. Each entry includes: parameters, return format, and realistic output examples.

Parameters marked with `?` are optional. The `db_path` parameter appears on every tool; it defaults to `.dominian/agentgraph.db` and is omitted from examples below for brevity.

---

### dominian_init

**Purpose**: Create the project database.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
✓ Initialized .dominian/agentgraph.db
```

If the database already exists with a compatible schema, the output is:
```
✓ Already initialized .dominian/agentgraph.db
```

---

### dominian_scan

**Purpose**: Scan the codebase and populate the database.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `path` | string | No | `.` |
| `db_path` | string | No | `.dominian/agentgraph.db` |
| `mode` | string | No | `"auto"` |
| `workers` | integer | No | `4` |

`mode` values: `"auto"`, `"sequential"`, `"threaded"`, `"process"`

**Output on success**:
```
✓ Scanned 147 files: 1,243 nodes, 3,891 edges (2.1s)
```

**Output when no source files found**:
```
⚠ No source files found in /empty/directory
```

**Output on parse errors** (errors are per-file, scan continues):
```
✓ Scanned 147 files: 1,243 nodes, 3,891 edges (2.1s)
⚠ 2 files had parse errors: malformed.py, broken.ts
```

---

### dominian_search

**Purpose**: Search for code entities by name. Case-insensitive substring match.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `query` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output** (results found):
```
🔍 5: process_payment, validate_payment, PaymentError, PaymentGateway, payment_callback
```

Format: `🔍 count: entity1, entity2, entity3`

**Output** (no results):
```
🔍 0:
```

The count prefix lets agents quickly determine if results exist without parsing the full list.

---

### dominian_node_get

**Purpose**: Get details for a single entity.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
📍 src/server.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3
```

Field breakdown:

| Field | Meaning | Example |
|-------|---------|---------|
| `📍` | Node marker | — |
| `src/server.py` | File path | Relative to project root |
| `handle_request` | Entity name | — |
| `42-89` | Start line – End line | Line range in the source file |
| `fn` | Type abbreviation | `fn`, `cls`, `mod`, `var`, `imp` |
| `c:12` | Cyclomatic complexity | Integer |
| `q:78.3` | Quality score | 0-100 float |
| `deps:5` | Direct dependency count | Integer |
| `used_by:3` | Direct reverse dependency count | Integer |

**Output for a class**:
```
📍 src/models.py:User:15-67 cls c:8 q:82.1 deps:3 used_by:12
```

**Output for a module**:
```
📍 src/utils.py:utils:1 mod c:0 q:91.0 deps:2 used_by:8
```

**Output when entity not found**:
```
ERR: Entity 'nonexistent_func' not found
```

---

### dominian_deps_direct

**Purpose**: List entities that this entity directly depends on (outgoing edges).

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
📥 handle_request→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls | src/models.py:Request:3(cls) uses
```

Format: `📥 entity→ dep1 relationship | dep2 relationship | dep3 relationship`

Each dependency includes: locator syntax `folder/file:name:line(type)` followed by the relationship type (`imports`, `calls`, `uses`, `depends_on`, `inherits`, `implements`).

**Output with no dependencies**:
```
📥 standalone_func→ (none)
```

---

### dominian_deps_reverse

**Purpose**: List entities that depend on this entity (incoming edges). Filters out `defines` edges because those represent parent-child containment (e.g., a class defines its methods), not usage.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
📤 get_conn← src/api/handler.py:process:22(fn) calls | src/jobs/worker.py:run_job:44(fn) calls | tests/test_db.py:test_conn:5(fn) calls
```

Format: `📤 entity← user1 relationship | user2 relationship`

**Output with no reverse dependencies**:
```
📤 unused_helper← (none)
```

This is a strong signal that the entity may be dead code (combine with `dominian_orphans` for confirmation).

---

### dominian_arch_impact

**Purpose**: Compute the transitive blast radius of changing an entity. Traverses the reverse dependency graph up to `depth` levels.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |
| `depth` | integer | No | `10` |

Risk levels:

| Level | Affected Count | Interpretation |
|-------|---------------|----------------|
| LOW | 0-2 | Change is localized |
| MEDIUM | 3-5 | Change ripples across a few modules |
| HIGH | 6-10 | Change affects significant portion of codebase |
| CRITICAL | 10+ | Change is architectural; proceed with caution |

**Output** (HIGH risk):
```
⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,email_notify,audit_log,report_gen
```

Format: `⚠️ LEVEL count:affected1,affected2,affected3,...`

**Output** (LOW risk):
```
⚠️ LOW 1:format_date
```

**Output** (CRITICAL risk):
```
⚠️ CRITICAL 14:app_init,router,middleware,auth_handler,db_pool,cache,logger,config,telemetry,...
```

The `depth` parameter controls how many hops to traverse. Default 10 is sufficient for most codebases. Reduce to 1 for direct-only impact:

```
dominian_arch_impact(entity="process_payment", depth=1)
  → ⚠️ MEDIUM 3:order_service,invoice_gen,payment_validator
```

---

### dominian_arch_communities

**Purpose**: Detect code communities using the Louvain modularity algorithm. Requires `dominian[communities]` extra.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
[4] [42,38,31,24] avg:33.8
```

Format: `[count] [size1,size2,...,sizeN] avg:mean_size`

Interpretation: 4 communities detected with sizes 42, 38, 31, and 24 entities. Average community size is 33.8.

**Output without community detection package**:
```
ERR: Community detection requires 'python-louvain'. Install with: pip install dominian[communities]
```

**Output when no edges exist**:
```
[0] [] avg:0
```

---

### dominian_arch_cross_community

**Purpose**: Find edges that cross community boundaries. These represent coupling between logical modules.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
🔗 src/api/auth.py:verify_token → src/db/users.py:find_user | src/api/routes.py:handle_order → src/payments/charge.py:process
```

Format: `🔗 from_entity → to_entity | from_entity → to_entity`

Each cross-community edge is a potential architectural violation or integration point. The number of cross-community edges relative to total edges indicates how tightly coupled the modules are.

**Output with no cross-community edges**:
```
🔗 (none)
```

This indicates clean modular boundaries.

---

### dominian_graph_stats

**Purpose**: Return high-level graph statistics.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
✓ 2847n 9431e q:74.2 Python
```

| Field | Meaning |
|-------|---------|
| `2847n` | Node count |
| `9431e` | Edge count |
| `q:74.2` | Average quality score across all entities |
| `Python` | Most common language in the codebase |

**Output before scanning**:
```
✓ 0n 0e q:0 ?
```

---

### dominian_graph_hotspots

**Purpose**: List entities with the highest composite score (complexity × connections × inverse quality). These are the most risky parts of the codebase.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `limit` | integer | No | `10` |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
🔥 47 c:24 q:42.1 | 38 c:18 q:55.3 | 31 c:21 q:48.7 | 27 c:15 q:61.2 | 22 c:19 q:52.8
```

Format: `🔥 ref_score c:complexity q:quality | ...`

The reference score (first number per entry) is a composite: it weights complexity, dependency count, and inverse quality. Higher scores indicate more dangerous code.

Each entry also has a locator when viewed in agent format. In minimal format, entity names are implied by ordering (match against `dominian_search` or `dominian_node_get` for specifics).

**Getting entity names for hotspots**: The minimal format omits entity names to save tokens. To identify which entity corresponds to a hotspot, use the agent or JSON format, or cross-reference by matching complexity/quality values:

```
dominian_nodes_by_quality(quality="low", limit=10)
```

---

### dominian_graph_cycles

**Purpose**: Detect circular dependencies using depth-first search with deduplication.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output** (cycles found):
```
🔄 3: A→B→C→A, D→E→D, F→G→H→F
```

Format: `🔄 count:cycle1,cycle2,...`

**Output** (no cycles):
```
🔄 0:
```

Cycles are returned in their traversal order. The same cycle is not reported in both directions (A→B→A and B→A→B are deduplicated).

---

### dominian_refactor_safe

**Purpose**: Determine whether an entity can be safely refactored (modified, moved, or deleted) without breaking dependents.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output** (safe):
```
✅ SAFE standalone_util
```

**Output** (not safe):
```
🚫 process_payment 4direct 12total dep_refs
```

| Field | Meaning |
|-------|---------|
| `4direct` | 4 entities directly depend on this |
| `12total` | 12 entities transitively depend on this |
| `dep_refs` | Indicator that dependency references exist |

When an entity is not safe, the agent should inspect `dominian_deps_reverse` for direct dependents and `dominian_arch_impact` for the full blast radius before proceeding.

---

### dominian_refactor_impact

**Purpose**: Alias for `dominian_arch_impact`. Same parameters, same output. Provided for semantic clarity in refactoring workflows.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |
| `depth` | integer | No | `10` |

---

### dominian_file_functions

**Purpose**: List all functions and methods defined in a file.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `file` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
📄 src/server.py 8fn: handle_request, parse_body, send_response, log_request, validate_headers, route_match, middleware_chain, error_handler
```

Format: `📄 file count: name1, name2, ...`

**Output for file with no functions**:
```
📄 src/constants.py 0fn:
```

**Output for file not in database**:
```
ERR: File 'nonexistent.py' not found in database
```

---

### dominian_file_classes

**Purpose**: List all classes defined in a file.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `file` | string | Yes | — |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
📄 src/models.py 4cls: User, Session, Token, Permission
```

**Output for file with no classes**:
```
📄 src/utils.py 0cls:
```

---

### dominian_info

**Purpose**: Show project status — whether the database exists, whether it has been scanned, and summary statistics.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output** (initialized and scanned):
```
✓ Initialized | 1,243 nodes | 3,891 edges | 7 languages | Last scan: 2025-05-04T14:32:00
```

**Output** (initialized but not scanned):
```
✓ Initialized | 0 nodes | 0 edges | Not scanned
```

**Output** (not initialized):
```
✗ Not initialized. Run dominian_init first.
```

---

### dominian_nodes_by_type

**Purpose**: List entities of a specific type.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `type` | string | Yes | — |
| `limit` | integer | No | `25` |
| `db_path` | string | No | `.dominian/agentgraph.db` |

Valid `type` values: `function`, `method`, `class`, `module`, `variable`, `import`, `dependency`

**Output**:
```
3: User, Session, Token
```

Format: `count: entity1, entity2, ...`

Note: The locator syntax is omitted in minimal format for list queries to maximize token density. Use `dominian_node_get` on individual entities for full details.

---

### dominian_nodes_by_quality

**Purpose**: List entities by quality score threshold.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `quality` | string | No | `"low"` |
| `limit` | integer | No | `15` |
| `db_path` | string | No | `.dominian/agentgraph.db` |

`quality` values:
- `"low"` — quality score < 70
- `"high"` — quality score >= 70

**Output** (low quality):
```
15: legacy_parser,q:32.1 | old_handler,q:38.7 | temp_fix,q:41.2 | monolith_func,q:43.8 | god_class,q:45.0 | ...
```

Format: `count: entity1,q:score | entity2,q:score | ...`

---

### dominian_god_nodes

**Purpose**: Identify highly-connected entities that serve as central hubs in the dependency graph. These are entities with abnormally high in-degree + out-degree.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `limit` | integer | No | `10` |
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
🔥 47 app_init | 🔥 38 router | 🔥 31 db_manager | 🔥 27 config_loader | 🔥 22 auth_middleware
```

Format: `🔥 connection_count entity_name`

God nodes are candidates for decomposition. If `app_init` has 47 connections, it's wiring together too many concerns and should be split.

---

### dominian_orphans

**Purpose**: Find entities with zero incoming and zero outgoing edges. These are potential dead code.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
🗑️ 12: unused_helper, old_migration, deprecated_util, test_fixture_a, ...
```

Format: `🗑️ count: entity1, entity2, ...`

**Output** (no orphans):
```
🗑️ 0:
```

Caveat: An orphan might be an entry point (e.g., `main()`) rather than dead code. Check whether the entity is called at runtime (e.g., via CLI, web framework routing, etc.) before removing it. Orphan detection is based on the static graph only.

---

### dominian_surprising_connections

**Purpose**: Find dependencies that cross top-level directory boundaries in unexpected ways. These indicate hidden coupling between modules that should be independent.

| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `db_path` | string | No | `.dominian/agentgraph.db` |

**Output**:
```
⚡ src/api/auth.py:verify_token → src/payments/stripe.py:charge_card | src/core/config.py:load → src/notifications/email.py:send
```

Format: `⚡ from → to | from → to`

Each surprising connection represents a dependency from one top-level directory (e.g., `api/`) to another (e.g., `payments/`) that may violate intended module boundaries. These are candidates for interface extraction or mediator patterns.

**Output** (no surprising connections):
```
⚡ (none)
```

---

## 5. Common Agent Patterns

Real-world agent workflows expressed as sequences of Dominian tool calls. Each pattern shows the exact calls and expected output.

### Pattern 1: "I need to change function X, what breaks?"

```
Call: dominian_arch_impact(entity="process_payment")
  → ⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,email_notify,audit_log,report_gen

Call: dominian_deps_reverse(entity="process_payment")
  → 📤 process_payment← src/api/orders.py:order_service:22(fn) calls | src/billing/invoice.py:invoice_gen:44(fn) calls | src/payments/validator.py:payment_validator:15(fn) calls | src/payments/refund.py:refund_handler:88(fn) calls
```

Decision: HIGH risk with 7 affected entities. The agent should:
1. Request human confirmation before proceeding.
2. Read the source of each reverse dependent to understand usage patterns.
3. Propose a backward-compatible change or a migration path.

### Pattern 2: "Find dead code"

```
Call: dominian_orphans()
  → 🗑️ 12: unused_helper, old_migration, deprecated_util, legacy_parser, ...

Call: dominian_deps_reverse(entity="unused_helper")
  → 📤 unused_helper← (none)

Call: dominian_refactor_safe(entity="unused_helper")
  → ✅ SAFE unused_helper
```

Confirmation: `unused_helper` has no reverse dependencies and is SAFE to remove. The orphan list provides candidates; `refactor_safe` confirms each one.

### Pattern 3: "Review this file"

```
Call: dominian_file_functions(file="src/server.py")
  → 📄 src/server.py 8fn: handle_request, parse_body, send_response, log_request, validate_headers, route_match, middleware_chain, error_handler

Call: dominian_file_classes(file="src/server.py")
  → 📄 src/server.py 2cls: Server, RequestHandler

Call: dominian_node_get(entity="handle_request")
  → 📍 src/server.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3

Call: dominian_deps_direct(entity="handle_request")
  → 📥 handle_request→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls | src/models.py:Request:3(cls) uses

Call: dominian_deps_reverse(entity="handle_request")
  → 📤 handle_request← src/api/router.py:dispatch:22(fn) calls | src/tests/test_server.py:test_handle:5(fn) calls | src/middleware/auth.py:wrap:31(fn) calls
```

The agent now has: all functions/classes in the file, complexity and quality for each entity, what each entity depends on, and what depends on each entity. This is sufficient context for a code review without reading the full source.

### Pattern 4: "Is this refactoring safe?"

```
Call: dominian_refactor_safe(entity="utility_function")
  → ✅ SAFE utility_function

Call: dominian_refactor_safe(entity="process_payment")
  → 🚫 process_payment 4direct 12total dep_refs
```

For the unsafe case, drill down:

```
Call: dominian_deps_reverse(entity="process_payment")
  → 📤 process_payment← src/api/orders.py:order_service:22(fn) calls | ...

Call: dominian_arch_impact(entity="process_payment", depth=3)
  → ⚠️ MEDIUM 5:order_service,invoice_gen,...
```

Decision: SAFE entities can be refactored freely. For unsafe entities, the agent must understand the blast radius and potentially update all dependents.

### Pattern 5: "Find circular dependencies"

```
Call: dominian_graph_cycles()
  → 🔄 2: config→database→config, auth→session→cache→auth
```

For each cycle, break down the participants:

```
Call: dominian_deps_direct(entity="config")
  → 📥 config→ src/db.py:database:1(mod) imports

Call: dominian_deps_direct(entity="database")
  → 📥 database→ src/config.py:config:1(mod) imports
```

This confirms the cycle: `config` imports `database`, and `database` imports `config`. The agent can suggest breaking this by introducing a shared module or using dependency injection.

### Pattern 6: "Understand project architecture"

```
Call: dominian_graph_stats()
  → ✓ 2847n 9431e q:74.2 Python

Call: dominian_arch_communities()
  → [5] [42,38,31,24,18] avg:30.6

Call: dominian_arch_cross_community()
  → 🔗 src/api/auth.py:verify_token → src/db/users.py:find_user | src/api/routes.py:handle_order → src/payments/charge.py:process

Call: dominian_god_nodes(limit=5)
  → 🔥 47 app_init | 🔥 38 router | 🔥 31 db_manager | 🔥 27 config_loader | 🔥 22 auth_middleware
```

Interpretation: 5 communities (logical modules), 2 cross-community coupling points, 5 god nodes that concentrate too many connections. The agent can report the modular structure and flag the coupling points for review.

### Pattern 7: "What are the riskiest parts of the codebase?"

```
Call: dominian_graph_hotspots(limit=10)
  → 🔥 47 c:24 q:42.1 | 🔥 38 c:18 q:55.3 | 🔥 31 c:21 q:48.7 | ...

Call: dominian_nodes_by_quality(quality="low", limit=10)
  → 10: legacy_parser,q:32.1 | old_handler,q:38.7 | temp_fix,q:41.2 | ...

Call: dominian_god_nodes(limit=5)
  → 🔥 47 app_init | 🔥 38 router | 🔥 31 db_manager | ...
```

Hotspots combine complexity + connections + low quality. Low-quality nodes are a subset of concern. God nodes indicate over-centralization. Together these three calls give a complete risk profile.

### Pattern 8: "Find coupling between independent modules"

```
Call: dominian_surprising_connections()
  → ⚡ src/api/auth.py:verify_token → src/payments/stripe.py:charge_card | src/core/config.py:load → src/notifications/email.py:send

Call: dominian_deps_direct(entity="verify_token")
  → 📥 verify_token→ src/payments/stripe.py:charge_card:88(fn) calls
```

The surprising connection from `auth` to `payments` is confirmed: the auth module directly calls a payment function. This is architectural coupling that shouldn't exist. The agent can suggest introducing an event system or mediator.

### Pattern 9: "Check if I can delete this unused feature"

```
Call: dominian_search(query="feature_flag")
  → 🔍 3: feature_flag, check_feature, FeatureFlagManager

Call: dominian_arch_impact(entity="FeatureFlagManager")
  → ⚠️ LOW 2:feature_flag,check_feature

Call: dominian_deps_reverse(entity="FeatureFlagManager")
  → 📤 FeatureFlagManager← src/flags/feature_flag.py:feature_flag:15(fn) calls | src/flags/check.py:check_feature:8(fn) calls

Call: dominian_deps_reverse(entity="feature_flag")
  → 📤 feature_flag← (none)

Call: dominian_deps_reverse(entity="check_feature")
  → 📤 check_feature← (none)
```

The entire feature flag subsystem is self-contained: `FeatureFlagManager` is only used by its own module's functions, and those functions have no external dependents. The agent can safely propose removal of all three entities.

### Pattern 10: "Prepare for a major version upgrade of a dependency"

```
Call: dominian_search(query="stripe")
  → 🔍 4: stripe_client, charge_card, refund_charge, StripeWebhook

Call: dominian_arch_impact(entity="stripe_client", depth=10)
  → ⚠️ HIGH 8:payment_handler,charge_card,refund_charge,StripeWebhook,invoice_service,subscription_mgr,billing_report,retry_queue

Call: dominian_deps_direct(entity="stripe_client")
  → 📥 stripe_client→ stripe.API.Client:1(imp) imports | stripe.API.Charge:1(imp) imports | stripe.API.Refund:1(imp) imports

Call: dominian_deps_reverse(entity="stripe_client")
  → 📤 stripe_client← src/payments/handler.py:payment_handler:22(fn) calls | src/payments/charge.py:charge_card:15(fn) calls | src/payments/refund.py:refund_charge:8(fn) calls | src/webhooks/stripe.py:StripeWebhook:3(cls) uses
```

The agent can now report: the Stripe integration touches 8 entities across payment handling, webhooks, billing, and retry logic. The 3 direct Stripe API imports are the upgrade surface. The agent can read just those 4 files to assess compatibility with the new Stripe API version.

### Pattern 11: "Understand a specific module before working on it"

```
Call: dominian_file_functions(file="src/auth/oauth.py")
  → 📄 src/auth/oauth.py 6fn: authorize, exchange_token, refresh_token, revoke_token, validate_scope, get_user_info

Call: dominian_file_classes(file="src/auth/oauth.py")
  → 📄 src/auth/oauth.py 1cls: OAuthClient

Call: dominian_deps_direct(entity="OAuthClient")
  → 📥 OAuthClient→ src/http/client.py:HttpClient:12(cls) uses | src/config.py:load_oauth:44(fn) calls | src/cache.py:token_cache:8(var) uses

Call: dominian_deps_reverse(entity="OAuthClient")
  → 📤 OAuthClient← src/auth/middleware.py:authenticate:31(fn) calls | src/auth/routes.py:login:15(fn) calls | src/auth/routes.py:callback:22(fn) calls
```

The agent now knows the module's public surface (6 functions + 1 class), its external dependencies (HttpClient, config, cache), and who uses it (middleware, routes). This is enough to work on the module without reading unrelated code.

### Pattern 12: "Identify test coverage gaps"

```
Call: dominian_search(query="test_")
  → 🔍 23: test_auth, test_payment, test_utils, ...

Call: dominian_nodes_by_type(type="function", limit=50)
  → 50: handle_request, process_payment, ...

Call: dominian_orphans()
  → 🗑️ 8: legacy_parser, temp_fix, ...
```

Orphans are never referenced, which includes never being called by tests. Cross-referencing the orphan list with production functions (not prefixed with `test_`) reveals untested code. Functions with zero reverse dependencies from test files are likely untested.

---

## 6. Output Format Guide

### Symbol Reference

| Symbol | Meaning | Context |
|--------|---------|---------|
| `📍` | Node (entity) | `dominian_node_get` |
| `📥` | Incoming/forward dependencies | `dominian_deps_direct` |
| `📤` | Outgoing/reverse dependencies | `dominian_deps_reverse` |
| `⚠️` | Impact/warning | `dominian_arch_impact` |
| `🔥` | Hotspot/god node | `dominian_graph_hotspots`, `dominian_god_nodes` |
| `🔄` | Cycle | `dominian_graph_cycles` |
| `✅` | Safe | `dominian_refactor_safe` |
| `🚫` | Not safe | `dominian_refactor_safe` |
| `📄` | File contents | `dominian_file_functions`, `dominian_file_classes` |
| `🔗` | Cross-community edge | `dominian_arch_cross_community` |
| `⚡` | Surprising connection | `dominian_surprising_connections` |
| `🗑️` | Orphan | `dominian_orphans` |
| `🔍` | Search results | `dominian_search` |
| `✓` | Success/status | `dominian_init`, `dominian_scan`, `dominian_graph_stats`, `dominian_info` |
| `✗` | Failure | `dominian_info` when not initialized |
| `ERR:` | Error | All tools on failure |

### Locator Syntax

The universal locator format identifies any entity in the codebase:

```
folder/file:name:line(type)
```

| Component | Description | Example |
|-----------|-------------|---------|
| `folder/file` | Last two path segments of the source file | `src/server.py` |
| `name` | Entity name | `handle_request` |
| `line` | Start line number | `42` |
| `type` | Abbreviated entity type | `fn` |

Type abbreviations:

| Abbreviation | Full Type | Description |
|-------------|-----------|-------------|
| `fn` | function/method | Functions and methods |
| `cls` | class | Classes |
| `mod` | module | Module-level entities |
| `var` | variable | Module-level variables |
| `imp` | import/dependency | Imported symbols |

Full locator example: `src/server.py:handle_request:42(fn)`

When the file is in the project root (no subdirectory), the path is a single segment: `main.py:run:10(fn)`

### Minimal Format Parsing Rules

1. **Delimiter between entries**: ` | ` (pipe with spaces)
2. **Delimiter within entries**: ` ` (space) between fields, `:` between structured fields
3. **Arrow direction**:
   - `→` means "depends on" (forward/outgoing edge)
   - `←` means "is used by" (reverse/incoming edge)
4. **Count prefixes**: Many outputs start with a count: `5:`, `12:`, `3fn:`, `4cls:`. Parse the number before the colon to determine list length.
5. **Empty results**: Indicated by `(none)` or `0:` depending on the tool.

### Node Detail Format

```
📍 file:name:start-end type c:complexity q:quality deps:N used_by:N
```

All fields are always present. Default values:
- `c:0` — complexity not computed (modules, variables)
- `q:100` — quality score defaults to 100 if no deductions
- `deps:0` / `used_by:0` — no connections

---

## 7. Token Optimization Tips

### Use the Right Tool for the Question

| Question | Efficient Tool | Inefficient Alternative |
|----------|---------------|------------------------|
| "Does X exist?" | `dominian_search` | Reading files |
| "What does X depend on?" | `dominian_deps_direct` | `dominian_node_get` then parsing |
| "Who uses X?" | `dominian_deps_reverse` | `dominian_search` + checking each result |
| "Is X safe to change?" | `dominian_refactor_safe` | `dominian_arch_impact` + manual analysis |
| "What breaks if I change X?" | `dominian_arch_impact` | Multiple `dominian_deps_reverse` calls |
| "What's in this file?" | `dominian_file_functions` + `dominian_file_classes` | Reading the entire file |
| "Find all classes" | `dominian_nodes_by_type(type="class")` | `dominian_search` with generic queries |

### Limit Result Sizes

Most tools have a `limit` parameter. Use it:

```
dominian_nodes_by_type(type="function", limit=10)  # Not 25
dominian_god_nodes(limit=3)                         # Not 10
dominian_graph_hotspots(limit=5)                    # Not 10
```

For `dominian_arch_impact`, reduce `depth` when you only need direct impact:

```
dominian_arch_impact(entity="X", depth=1)  # Direct dependents only
```

### Batch Related Queries

When reviewing a file, get both functions and classes in one logical step:

```
dominian_file_functions(file="src/server.py")
dominian_file_classes(file="src/server.py")
```

These are two calls but they replace reading the entire file.

### Prefer Search Over Browse

```
dominian_search(query="payment")
```

This is more token-efficient than listing all entities and filtering. The search returns only matching names.

### Use Refactor Safe as a Gate

Before doing deep analysis on an entity, check if it's safe:

```
dominian_refactor_safe(entity="X")
  → ✅ SAFE X
```

If SAFE, no further dependency analysis is needed. Skip the `arch_impact` and `deps_reverse` calls.

### Choose Depth Wisely for Impact Analysis

| Depth | Use Case | Token Cost |
|-------|----------|-----------|
| 1 | Direct dependents only | Lowest |
| 3 | Immediate neighborhood | Low |
| 10 | Full blast radius (default) | Medium |
| 10+ | Rarely needed; most graphs are shallow | Higher |

### Re-scan Only When Necessary

Content-hash caching means re-scanning is cheap when files haven't changed. But if you know no files have changed since the last scan, skip `dominian_scan` entirely and go straight to queries.

### Approximate Token Costs

Rough estimates for minimal-format output:

| Tool | Typical Token Count | Notes |
|------|-------------------|-------|
| `dominian_info` | ~15 | Single line |
| `dominian_graph_stats` | ~10 | Single line |
| `dominian_search` | 10-50 | Depends on match count |
| `dominian_node_get` | ~25 | Single entity |
| `dominian_deps_direct` | 20-80 | Depends on dependency count |
| `dominian_deps_reverse` | 20-80 | Depends on dependent count |
| `dominian_arch_impact` | 15-60 | Depends on blast radius |
| `dominian_refactor_safe` | ~10 | Single line |
| `dominian_graph_cycles` | 10-100 | Depends on cycle count |
| `dominian_graph_hotspots` | 30-80 | Depends on limit |
| `dominian_arch_communities` | ~15 | Single line |
| `dominian_orphans` | 10-100 | Depends on orphan count |
| `dominian_file_functions` | 20-60 | Depends on function count |

For comparison, reading a typical source file costs 200-800 tokens. A single `dominian_deps_reverse` call at ~40 tokens replaces reading 5-10 files at 1,000-8,000 tokens.

---

## 8. Error Handling

### ERR: Responses

All tools return errors in the format:

```
ERR: Description of the error
```

Common error patterns:

| Error | Cause | Resolution |
|-------|-------|------------|
| `ERR: Entity 'X' not found` | Entity doesn't exist in the database | Verify spelling with `dominian_search`. Entity names are case-sensitive. |
| `ERR: File 'X' not found in database` | File wasn't scanned or path is wrong | Verify path with `dominian_search` for entities in that file. |
| `ERR: Database not found at X` | No database at the specified path | Run `dominian_init` first. |
| `ERR: Database not initialized` | Schema doesn't exist | Run `dominian_init`. |
| `ERR: Community detection requires 'python-louvain'` | Missing optional dependency | Install with `pip install dominian[communities]` |
| `ERR: Scan failed: ...` | File system error during scan | Check path exists and is readable. |

### Exit Codes (CLI Only)

When using the CLI directly (not MCP), exit codes indicate result type:

| Exit Code | Meaning | Agent Action |
|-----------|---------|-------------|
| 0 | Success with results | Parse output normally |
| 1 | Success but no results (e.g., search found nothing) | Treat as empty result set, not an error |
| 2 | Error (invalid arguments, database failure) | Report the error to the user |

Note: MCP tools do not use exit codes. Errors are returned as `ERR:` strings in the tool response.

### Empty Results vs Errors

| Scenario | Output | Is Error? |
|----------|--------|-----------|
| Search finds nothing | `🔍 0:` | No — legitimate empty result |
| Entity not found | `ERR: Entity 'X' not found` | Yes — entity doesn't exist |
| No orphans | `🗑️ 0:` | No — legitimate empty result |
| No cycles | `🔄 0:` | No — legitimate empty result |
| Database not initialized | `ERR: Database not initialized` | Yes — prerequisite not met |

### Handling Ambiguous Entity Names

If `dominian_node_get` returns `ERR: Entity not found`, the entity name might be ambiguous or differ from what you expect:

```
dominian_search(query="validate")
  → 🔍 8: validate_input, validate_output, validate_email, validate_schema, ...

dominian_node_get(entity="validate_input")
  → 📍 src/utils.py:validate_input:8-22 fn c:5 q:88.1 deps:2 used_by:7
```

Always use `dominian_search` to discover exact entity names before using `dominian_node_get`, `dominian_deps_direct`, etc.

### Database Lock Errors

Under concurrent access (e.g., scanning while querying), you may encounter:

```
ERR: Database is locked
```

This is rare with WAL mode but can occur under heavy write contention. Resolution: wait and retry. The WAL mode allows concurrent reads during writes, so this typically resolves within milliseconds.

---

## 9. Multi-Step Workflows

### Workflow 1: Full Architecture Review

Based on the `architecture_review` MCP prompt. 8 steps.

```
Step 1: Assess overall structure
  dominian_graph_stats()
    → ✓ 2847n 9431e q:74.2 Python

Step 2: Detect communities (logical modules)
  dominian_arch_communities()
    → [5] [42,38,31,24,18] avg:30.6

Step 3: Find cross-module coupling
  dominian_arch_cross_community()
    → 🔗 src/api/auth.py:verify_token → src/db/users.py:find_user | src/api/routes.py:handle_order → src/payments/charge.py:process

Step 4: Identify central hubs
  dominian_god_nodes(limit=5)
    → 🔥 47 app_init | 🔥 38 router | 🔥 31 db_manager | 🔥 27 config_loader | 🔥 22 auth_middleware

Step 5: Find architectural violations
  dominian_surprising_connections()
    → ⚡ src/api/auth.py:verify_token → src/payments/stripe.py:charge_card | src/core/config.py:load → src/notifications/email.py:send

Step 6: Assess code quality distribution
  dominian_nodes_by_quality(quality="low", limit=15)
    → 15: legacy_parser,q:32.1 | old_handler,q:38.7 | temp_fix,q:41.2 | ...

Step 7: Detect circular dependencies
  dominian_graph_cycles()
    → 🔄 2: config→database→config, auth→session→cache→auth

Step 8: Identify dead code
  dominian_orphans()
    → 🗑️ 12: unused_helper, old_migration, deprecated_util, ...
```

Synthesis: The agent can now produce a structured architecture report:
- 5 modules with clean boundaries except 2 cross-community coupling points
- 2 surprising cross-directory dependencies that violate module independence
- 5 god nodes that need decomposition
- 2 circular dependency chains to break
- 15 low-quality entities requiring attention
- 12 orphaned entities that may be dead code

### Workflow 2: Code Review with Dependency Context

Based on the `code_review` MCP prompt. 5 steps.

```
Step 1: Get entity details
  dominian_node_get(entity="process_payment")
    → 📍 src/payments/service.py:process_payment:88-156 fn c:18 q:65.2 deps:7 used_by:4

Step 2: Understand what it depends on
  dominian_deps_direct(entity="process_payment")
    → 📥 process_payment→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls | src/models.py:Payment:3(cls) uses | src/gateway.py:charge:22(fn) calls | src/logger.py:log:5(fn) calls | src/config.py:get_key:44(fn) calls | src/errors.py:PaymentError:1(cls) uses

Step 3: Understand what depends on it
  dominian_deps_reverse(entity="process_payment")
    → 📤 process_payment← src/api/orders.py:order_service:22(fn) calls | src/billing/invoice.py:invoice_gen:44(fn) calls | src/payments/refund.py:refund_handler:88(fn) calls | src/jobs/retry.py:retry_payment:15(fn) calls

Step 4: Assess change risk
  dominian_arch_impact(entity="process_payment")
    → ⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,email_notify,audit_log,report_gen

Step 5: Check refactoring safety
  dominian_refactor_safe(entity="process_payment")
    → 🚫 process_payment 4direct 12total dep_refs
```

The agent now has complete context for a code review:
- Complexity 18 is high (cyclomatic); the function has many branches
- Quality 65.2 is below the 70 threshold; improvements needed
- 7 direct dependencies suggest the function does too much (possible SRP violation)
- 4 direct reverse dependents and 12 total; changes will propagate widely
- HIGH risk rating; any changes require careful testing

### Workflow 3: Refactoring Plan

Based on the `refactor_plan` MCP prompt. 5 steps.

```
Step 1: Confirm refactoring is viable
  dominian_refactor_safe(entity="process_payment")
    → 🚫 process_payment 4direct 12total dep_refs

Step 2: Map the full impact radius
  dominian_arch_impact(entity="process_payment", depth=10)
    → ⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,email_notify,audit_log,report_gen

Step 3: Identify the dependency chain
  dominian_deps_direct(entity="process_payment")
    → 📥 process_payment→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls | src/models.py:Payment:3(cls) uses | src/gateway.py:charge:22(fn) calls | src/logger.py:log:5(fn) calls | src/config.py:get_key:44(fn) calls | src/errors.py:PaymentError:1(cls) uses

Step 4: Identify all consumers that need updating
  dominian_deps_reverse(entity="process_payment")
    → 📤 process_payment← src/api/orders.py:order_service:22(fn) calls | src/billing/invoice.py:invoice_gen:44(fn) calls | src/payments/refund.py:refund_handler:88(fn) calls | src/jobs/retry.py:retry_payment:15(fn) calls

Step 5: Check for cycles that would block extraction
  dominian_graph_cycles()
    → 🔄 2: config→database→config, auth→session→cache→auth
```

Refactoring plan based on the data:
1. `process_payment` is NOT safe to refactor directly — 4 direct, 12 total dependents.
2. The function depends on 7 other entities, suggesting it should be split (e.g., separate payment validation, gateway communication, and logging).
3. Before refactoring, the 4 direct consumers must be updated to use the new interface.
4. No cycles involve `process_payment`, so extraction is topologically possible.
5. The existing cycles (config↔database, auth→session→cache→auth) are unrelated and don't block this refactoring.

### Workflow 4: Onboarding to an Unfamiliar Codebase

```
Step 1: Get the big picture
  dominian_graph_stats()
    → ✓ 2847n 9431e q:74.2 Python

Step 2: Identify logical modules
  dominian_arch_communities()
    → [5] [42,38,31,24,18] avg:30.6

Step 3: Find the most important entities
  dominian_god_nodes(limit=10)
    → 🔥 47 app_init | 🔥 38 router | 🔥 31 db_manager | 🔥 27 config_loader | 🔥 22 auth_middleware | ...

Step 4: Find the riskiest code
  dominian_graph_hotspots(limit=10)
    → 🔥 47 c:24 q:42.1 | 🔥 38 c:18 q:55.3 | ...

Step 5: Find architectural concerns
  dominian_surprising_connections()
    → ⚡ src/api/auth.py:verify_token → src/payments/stripe.py:charge_card

Step 6: Drill into the entry point
  dominian_deps_direct(entity="app_init")
    → 📥 app_init→ src/db.py:db_manager:12(fn) calls | src/config.py:config_loader:44(fn) calls | src/auth.py:auth_middleware:8(fn) calls | ...

Step 7: Find what the router connects
  dominian_deps_reverse(entity="router")
    → 📤 router← src/api/orders.py:order_service:22(fn) calls | src/api/auth.py:login:15(fn) calls | ...
```

This 7-call sequence gives the agent a comprehensive understanding of the codebase: its size, structure, important entities, risky areas, and how the main components connect.

### Workflow 5: Pre-Commit Safety Check

Before committing changes to entity X:

```
Step 1: Verify the entity still exists after edits
  dominian_search(query="process_payment")
    → 🔍 1: process_payment

Step 2: Re-scan to pick up changes
  dominian_scan(path=".")
    → ✓ Scanned 147 files: 1,251 nodes, 3,912 edges (0.4s)

Step 3: Check if new dependencies were introduced
  dominian_deps_direct(entity="process_payment")
    → 📥 process_payment→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls | src/new_module.py:new_func:5(fn) calls

Step 4: Verify impact hasn't grown
  dominian_arch_impact(entity="process_payment")
    → ⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,email_notify,audit_log,report_gen

Step 5: Confirm no new cycles were introduced
  dominian_graph_cycles()
    → 🔄 2: config→database→config, auth→session→cache→auth
```

Compare the new output with the pre-edit baseline. Any new dependencies, increased impact radius, or new cycles indicate the change had unintended side effects.

---

## Appendix: MCP Resources and Prompts

### Resources

Resources are read-only data that the MCP client can access without tool calls.

**`dominian://status`** — Current project status. Equivalent to calling `dominian_info`.

**`dominian://schema`** — Database schema information. Returns the table definitions and index list. Useful for understanding what data is available for direct SQL queries (advanced use).

### Prompts

Prompts are pre-built workflow templates that the MCP client can invoke to guide the agent through a multi-step process.

**`code_review(entity)`** — 5-step code review:
1. Get entity details
2. Examine dependencies
3. Examine reverse dependencies
4. Assess impact
5. Check refactoring safety

**`architecture_review()`** — 8-step architecture review:
1. Graph statistics
2. Community detection
3. Cross-community edges
4. God nodes
5. Surprising connections
6. Quality distribution
7. Circular dependencies
8. Orphan detection

**`refactor_plan(entity)`** — 5-step refactoring plan:
1. Check refactoring safety
2. Map impact radius
3. Identify dependency chain
4. Identify consumers
5. Check for blocking cycles

These prompts are templates. The agent fills in the tool calls based on the prompt's instructions. They do not execute tools automatically.

---

## Appendix: Type System Reference

### Entity Types

| Type | Abbreviation | Description | Typical Quality Impact |
|------|-------------|-------------|----------------------|
| `function` | `fn` | Standalone function | Complexity-based deductions |
| `method` | `fn` | Class method (shown as `fn` in output) | Complexity-based deductions |
| `class` | `cls` | Class definition | Deductions for size, coupling |
| `module` | `mod` | Module-level entity | Typically high quality |
| `variable` | `var` | Module-level variable | Typically high quality |
| `import` | `imp` | Import/dependency | Neutral |
| `dependency` | `imp` | External dependency | Neutral |

Note: Functions and methods share the `fn` abbreviation. To distinguish them, use `dominian_node_get` — the full type string in the node detail distinguishes `function` from `method`.

### Edge Types (Relationships)

| Relationship | Direction | Description |
|-------------|-----------|-------------|
| `imports` | A → B | A imports B |
| `depends_on` | A → B | A depends on B (general) |
| `uses` | A → B | A uses/references B |
| `calls` | A → B | A calls B (function/method call) |
| `defines` | A → B | A defines B (e.g., class defines method) |
| `inherits` | A → B | A inherits from B |
| `implements` | A → B | A implements interface B |

The `defines` relationship is filtered from `dominian_deps_reverse` output because it represents containment (a class contains its methods), not usage. A method defined by a class is not "using" the class in the dependency sense.

---

## Appendix: Scan Mode Selection Guide

| File Count | Auto-Selected Mode | Rationale |
|-----------|-------------------|-----------|
| < 50 | `sequential` | Overhead of parallelism exceeds benefit |
| 50 - 500 | `threaded` | Thread pool shares memory; WAL handles concurrent writes |
| > 500 | `process` | Process pool avoids GIL; `spawn` method for isolation |

Forcing a specific mode:

```
dominian_scan(path=".", mode="sequential")  # Deterministic, debuggable
dominian_scan(path=".", mode="process", workers=8)  # Large monorepo
```

The `workers` parameter has no effect in `sequential` mode.
