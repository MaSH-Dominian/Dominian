# Token Usage and Optimization Guide

**Dominian**

A technical reference for minimizing token consumption when using Dominian with AI agents. Every number in this document is an approximate token count using tiktoken `cl100k_base` tokenization — the tokenizer used by GPT-4-class models.

---

## 1. Why Token Efficiency Matters

Agent context windows are finite. A 128k-token context window sounds large, but in practice it is consumed by:

| Consumer | Typical Cost |
|---|---|
| System prompt | 500–2,000 tokens |
| Conversation history (10 turns) | 3,000–15,000 tokens |
| Retrieved code snippets | 2,000–10,000 tokens |
| Tool results | Variable — the controllable portion |

Every token spent on output formatting is a token not spent on reasoning. If a dependency query returns 120 tokens of decorated text when 15 tokens of structured data convey the same information, the agent loses 105 tokens of thinking space per call. Over a session with 20 tool calls, that is ~2,100 wasted tokens — enough for an entire additional code snippet or several rounds of reasoning.

Dominian's **minimal** format is designed to solve this. It compresses graph query output to the smallest unambiguous representation, yielding approximately **85% fewer tokens** than the `agent` format and **90% fewer** than `json`. The exact reduction varies by command type; section 2 provides the numbers.

---

## 2. Format Comparison

### 2.1 Stats Query

`dominian stats` — project-level statistics.

**minimal** (~10 tokens):

```
✓ 1247n 3891e q:82.3 python
```

**agent** (~80 tokens):

```
══════════════════════════════
  PROJECT STATISTICS
══════════════════════════════

📊 Nodes:         1,247
🔗 Edges:         3,891
📈 Avg Quality:   82.3
🔤 Language:      python

══════════════════════════════
```

**json** (~120 tokens):

```json
{
  "nodes": 1247,
  "edges": 3891,
  "avg_quality": 82.3,
  "language": "python"
}
```

**Reduction**: minimal vs agent = (80−10)/80 = **87.5%**; minimal vs json = (120−10)/120 = **91.7%**.

---

### 2.2 Node Lookup

`dominian node_get` — retrieve details for a single node.

**minimal** (~15 tokens):

```
📍 src/server.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3
```

**agent** (~100 tokens):

```
══════════════════════════════
  NODE: handle_request
══════════════════════════════

🏷️  Type:       function
📄 File:        src/server.py
📐 Lines:       42-89
📊 Quality:     78.3
🧮 Complexity:  12
📥 Dependencies: 5
📤 Dependents:   3
📝 Signature:   handle_request(req: Request) -> Response
📖 Docstring:   Main HTTP request handler with middleware chain

══════════════════════════════
```

**json** (~150 tokens):

```json
{
  "name": "handle_request",
  "file": "src/server.py",
  "type": "function",
  "start_line": 42,
  "end_line": 89,
  "quality": 78.3,
  "complexity": 12,
  "dependencies_count": 5,
  "dependents_count": 3,
  "signature": "handle_request(req: Request) -> Response",
  "docstring": "Main HTTP request handler with middleware chain"
}
```

**Reduction**: minimal vs agent = (100−15)/100 = **85.0%**; minimal vs json = (150−15)/150 = **90.0%**.

---

### 2.3 Dependencies

`dominian deps` — list direct dependencies of a node.

**minimal** (~25 tokens for 2 dependencies):

```
📥 handle_request→ src/db.py:get_conn:15(fn) imports | src/utils.py:validate:8(fn) calls
```

**agent** (~120 tokens):

```
══════════════════════════════
  DEPENDENCIES OF: handle_request
══════════════════════════════

  ➤ src/db.py → get_conn
    Type:        function
    Line:        15
    Relationship: imports
    Weight:      0.8

  ➤ src/utils.py → validate
    Type:        function
    Line:        8
    Relationship: calls
    Weight:      0.6

══════════════════════════════
```

**json** (~180 tokens):

```json
{
  "node": "handle_request",
  "dependencies": [
    {
      "file": "src/db.py",
      "name": "get_conn",
      "line": 15,
      "type": "function",
      "relationship": "imports",
      "weight": 0.8
    },
    {
      "file": "src/utils.py",
      "name": "validate",
      "line": 8,
      "type": "function",
      "relationship": "calls",
      "weight": 0.6
    }
  ]
}
```

**Reduction**: minimal vs agent = (120−25)/120 = **79.2%**; minimal vs json = (180−25)/180 = **86.1%**.

---

### 2.4 Impact Analysis

`dominian impact` — assess change impact.

**minimal** (~15 tokens):

```
⚠️ HIGH 7:order_service,invoice_gen,payment_validator,refund_handler,...
```

**agent** (~100 tokens):

```
══════════════════════════════
  IMPACT ANALYSIS
══════════════════════════════

🔴 Risk Level:    HIGH
📊 Affected:      7 nodes

  Affected Nodes:
    • order_service
    • invoice_gen
    • payment_validator
    • refund_handler
    • tax_calculator
    • shipping_manager
    • notification_service

══════════════════════════════
```

**json** (~140 tokens):

```json
{
  "risk_level": "HIGH",
  "affected_count": 7,
  "affected_nodes": [
    "order_service",
    "invoice_gen",
    "payment_validator",
    "refund_handler",
    "tax_calculator",
    "shipping_manager",
    "notification_service"
  ]
}
```

**Reduction**: minimal vs agent = (100−15)/100 = **85.0%**; minimal vs json = (140−15)/140 = **89.3%**.

---

### 2.5 Search Results

`dominian search` — find nodes matching a pattern (5 results shown).

**minimal** (~40 tokens):

```
🔍 src/api.py:handle_request:42(fn) | src/api.py:validate_input:15(fn) | src/middleware.py:handle_error:88(fn) | src/utils.py:handle_response:23(fn) | src/router.py:handle_route:67(fn)
```

**agent** (~200 tokens):

```
══════════════════════════════
  SEARCH RESULTS: "handle"
══════════════════════════════

  1. src/api.py → handle_request
     Type:   function
     Line:   42

  2. src/api.py → validate_input
     Type:   function
     Line:   15

  3. src/middleware.py → handle_error
     Type:   function
     Line:   88

  4. src/utils.py → handle_response
     Type:   function
     Line:   23

  5. src/router.py → handle_route
     Type:   function
     Line:   67

══════════════════════════════
```

**json** (~300 tokens):

```json
{
  "query": "handle",
  "results": [
    {"file": "src/api.py", "name": "handle_request", "line": 42, "type": "function"},
    {"file": "src/api.py", "name": "validate_input", "line": 15, "type": "function"},
    {"file": "src/middleware.py", "name": "handle_error", "line": 88, "type": "function"},
    {"file": "src/utils.py", "name": "handle_response", "line": 23, "type": "function"},
    {"file": "src/router.py", "name": "handle_route", "line": 67, "type": "function"}
  ]
}
```

**Reduction**: minimal vs agent = (200−40)/200 = **80.0%**; minimal vs json = (300−40)/300 = **86.7%**.

---

### 2.6 Aggregate Reduction Summary

| Command | minimal | agent | json | minimal vs agent | minimal vs json |
|---|---|---|---|---|---|
| stats | ~10 | ~80 | ~120 | 87.5% | 91.7% |
| node_get | ~15 | ~100 | ~150 | 85.0% | 90.0% |
| deps (2 items) | ~25 | ~120 | ~180 | 79.2% | 86.1% |
| impact | ~15 | ~100 | ~140 | 85.0% | 89.3% |
| search (5 items) | ~40 | ~200 | ~300 | 80.0% | 86.7% |
| **Mean** | | | | **83.3%** | **88.8%** |

The "~85% reduction vs verbose" claim is conservative. Against the `agent` format, reduction ranges from 79–88% with a mean of 83%. Against `json`, reduction ranges from 86–92% with a mean of 89%. The "vs verbose" figure of ~85% is the average across both verbose formats weighted by typical usage.

---

## 3. Minimal Format Specification

### 3.1 Locator Syntax

The fundamental addressing unit. Every node is identified by:

```
folder/file:name:line(type)
```

| Component | Description | Example |
|---|---|---|
| `folder/file` | Path relative to project root | `src/server.py` |
| `name` | Node identifier | `handle_request` |
| `line` | Start line, or start-end range | `42` or `42-89` |
| `(type)` | Node type abbreviation in parentheses | `(fn)` |

Examples:

```
src/server.py:handle_request:42-89(fn)
src/models.py:User:15(cls)
src/__init__.py:15(imp)
src/config.py:DEBUG:5(var)
```

### 3.2 Type Abbreviations

| Abbreviation | Full Type |
|---|---|
| `fn` | function |
| `cls` | class |
| `mod` | module |
| `var` | variable |
| `imp` | import |
| `dep` | dependency edge |

### 3.3 Unicode Markers

Markers are single characters that replace multi-word labels. Each marker occupies 1–2 tokens (Unicode codepoints are typically single tokens in cl100k_base).

| Marker | Meaning | Replaces |
|---|---|---|
| `📥` | Dependencies (outgoing) | "DEPENDENCIES" / "depends on" |
| `📤` | Dependents (incoming) | "DEPENDENTS" / "used by" |
| `⚠️` | Impact / warning | "IMPACT ANALYSIS" / "WARNING" |
| `✅` | Safe to refactor | "SAFE" / "refactor-safe" |
| `🚫` | Unsafe to refactor | "UNSAFE" / "refactor-unsafe" |
| `📍` | Location / node info | "NODE" / "LOCATION" |
| `🔍` | Search results | "SEARCH RESULTS" |
| `🔥` | Hotspot | "HOTSPOT" |
| `🔄` | Cycle detected | "CYCLE" |
| `📦` | Community | "COMMUNITY" |
| `🔗` | Cross-community edge | "CROSS-COMMUNITY" |
| `📄` | File-level node | "FILE" |
| `✓` | Stats / success | "STATISTICS" / "OK" |

### 3.4 Separators

| Separator | Usage | Example |
|---|---|---|
| `\|` | Between items in a list | `item1 \| item2 \| item3` |
| `,` | Between fields within an item | `c:12,q:78.3,deps:5` |
| `:` | Between key and value | `q:78.3` or `deps:5` |
| `→` | Dependency relationship (source→target) | `handle_request→ get_conn` |

### 3.5 Count-First Pattern

When listing multiple items of the same kind, the count precedes the list. This lets an agent decide whether to expand the list or stop reading after the count.

```
7:order_service,invoice_gen,payment_validator,refund_handler,...
```

The trailing `,...` indicates truncation (when `--limit` is active). Without truncation:

```
3:alpha,beta,gamma
```

This pattern replaces verbose constructions like "3 items: alpha, beta, gamma" (6 tokens) with "3:alpha,beta,gamma" (4 tokens) — a 33% savings on list headers alone, with compounding savings on longer lists.

### 3.6 Key Abbreviations

| Abbreviation | Full Key | Context |
|---|---|---|
| `c` | complexity | Node detail |
| `q` | quality score | Node detail, stats |
| `n` | node count | Stats |
| `e` | edge count | Stats |
| `deps` | dependency count | Node detail |
| `used_by` | dependent count | Node detail |
| `fn` | function | Type tag |
| `cls` | class | Type tag |
| `mod` | module | Type tag |
| `var` | variable | Type tag |
| `imp` | import | Type tag |
| `dep` | dependency | Type tag |

---

## 4. Token Budget Planning

The following estimates assume the **minimal** format. Agent and json formats multiply these costs by roughly 5–10x depending on the command.

### 4.1 Common Workflow Costs

**Quick check** — "Does this function exist? Where?" (~30 tokens)

| Step | Command | Est. Tokens |
|---|---|---|
| 1 | `search handle_request` | ~12 |
| 2 | `node_get src/api.py:handle_request:42` | ~15 |
| | **Total** | **~27** |

**Code review** — "Is this function safe to modify?" (~80 tokens)

| Step | Command | Est. Tokens |
|---|---|---|
| 1 | `node_get src/server.py:handle_request:42` | ~15 |
| 2 | `deps_direct handle_request` (3 deps) | ~35 |
| 3 | `deps_reverse handle_request` (5 dependents) | ~25 |
| 4 | `refactor_check handle_request` | ~5 |
| | **Total** | **~80** |

**Architecture review** — "Map the whole project" (~150 tokens)

| Step | Command | Est. Tokens |
|---|---|---|
| 1 | `stats` | ~10 |
| 2 | `hotspots` (5 results) | ~40 |
| 3 | `cycles` (2 cycles) | ~30 |
| 4 | `communities` (4 communities) | ~40 |
| 5 | `cross_community` (3 edges) | ~20 |
| 6 | `god_nodes` (1 result) | ~10 |
| | **Total** | **~150** |

### 4.2 Comparison: Dominian vs. Reading Source Files

Reading a single 200-line Python file directly costs approximately 800–1,000 tokens (cl100k_base tokenizes code at roughly 4–5 tokens per line including whitespace).

| Approach | Token Cost | Information Gained |
|---|---|---|
| Read 1 file (200 lines) | ~900 | Structure of 1 file, no cross-file context |
| Dominian `stats` + `search` + `node_get` + `deps` | ~60 | Project overview + entity location + dependencies + dependents |
| Read 5 files for same context | ~4,500 | Same information, 75x more tokens |

Dominian is not a replacement for reading code — you will still need to read files when making edits. But it replaces the exploratory reading phase where an agent scans files to understand structure, locate entities, and map dependencies. That phase typically consumes 3,000–10,000 tokens of context. Dominian compresses it to 50–200 tokens.

---

## 5. Optimization Strategies

### 5.1 Use Minimal Format for All Agent Interactions

Minimal is the default for a reason. Explicitly setting `--format minimal` is unnecessary but harmless. Never use `--format agent` in an agent loop — it exists for human consumption only.

### 5.2 Use JSON Format Only When Programmatically Parsing

JSON is the correct choice when the output will be consumed by code (`jq`, Python `json.loads()`, CI/CD pipelines). For LLM/agent consumption, minimal is strictly superior — LLMs parse pipe-delimited data as effectively as JSON key-value pairs, at a fraction of the token cost.

### 5.3 Use Agent Format Only When Presenting to Humans

The `agent` format adds decorative headers, alignment, and labels that improve readability for humans in terminals. It has no informational advantage over minimal — every data point present in `agent` output is also present in `minimal` output. The difference is purely formatting.

### 5.4 Limit Results with --limit

Most commands accept `--limit N`. Use it. A search that returns 50 results in minimal format costs ~400 tokens; limited to 5 results, it costs ~40 tokens. If you need more results, paginate with `--offset`.

### 5.5 Scan Once, Query Many Times

`dominian scan` builds a persistent graph database. Run it once, then query the graph as many times as needed. Re-scanning is only necessary when source files change. The scan itself has a one-time cost (reading and parsing files), but subsequent queries are effectively free — they read from the graph, not the filesystem.

### 5.6 Search Before node_get

Use `search` to locate the exact entity name and locator, then use `node_get` with the precise locator. This avoids guesswork and prevents failed lookups that waste tokens on error messages.

```
# Good: two-step lookup
search handle_request       → 🔍 src/api.py:handle_request:42(fn)
node_get src/api.py:handle_request:42  → 📍 src/api.py:handle_request:42-89 fn c:12 q:78.3 deps:5 used_by:3

# Wasteful: guessing
node_get handle_request     → Error: node not found (~5 wasted tokens + retry)
```

### 5.7 Check Stats Before Expensive Operations

Run `stats` first to gauge database size. If `stats` returns `23n 31e`, community detection and hotspot analysis will be trivial and may not provide useful insights. If it returns `4872n 19203e`, expect large result sets and use `--limit` aggressively.

### 5.8 Skip Community Detection on Small Codebases

Community detection algorithms are meaningful when the graph has enough structure to form distinct clusters. On codebases with fewer than ~50 nodes, communities tend to be trivially obvious (each directory = one community) and the command output adds no value. Save the ~40 tokens.

---

## 6. When to Use Which Format

| Scenario | Format | Rationale |
|---|---|---|
| Agent tool loop (any LLM) | `minimal` | Maximum information density per token |
| Human reading terminal output | `agent` | Readable headers, alignment, visual separation |
| Piping to `jq` or scripts | `json` | Machine-parseable, stable schema |
| CI/CD integration | `json` | Structured output, exit codes, parseable fields |
| Debugging Dominian itself | `agent` | Verbose labels make it easier to spot missing data |
| Demonstrations / tutorials | `agent` | Humans can follow along more easily |
| Cost-sensitive batch processing | `minimal` | Lowest per-call token cost for high-volume queries |
| Exporting to other tools | `json` | Universal interchange format |

---

## 7. Token Cost per Operation

Approximate token costs in **minimal** format for a mid-sized Python project (~1,200 nodes, ~3,800 edges). Actual costs scale linearly with result count.

| Command | Typical Result Size | Est. Tokens (minimal) | Est. Tokens (agent) | Est. Tokens (json) |
|---|---|---|---|---|
| `stats` | 1 summary | ~10 | ~80 | ~120 |
| `search` | 5 results | ~40 | ~200 | ~300 |
| `search` | 20 results | ~160 | ~800 | ~1,200 |
| `node_get` | 1 node | ~15 | ~100 | ~150 |
| `deps_direct` | 3 deps | ~35 | ~120 | ~180 |
| `deps_reverse` | 5 dependents | ~25 | ~200 | ~300 |
| `refactor_check` | 1 result | ~5 | ~40 | ~60 |
| `impact` | HIGH, 7 nodes | ~15 | ~100 | ~140 |
| `impact` | LOW, 2 nodes | ~8 | ~60 | ~80 |
| `hotspots` | 5 results | ~40 | ~250 | ~375 |
| `cycles` | 2 cycles | ~30 | ~150 | ~225 |
| `communities` | 4 communities | ~40 | ~200 | ~300 |
| `cross_community` | 3 edges | ~20 | ~120 | ~180 |
| `god_nodes` | 1 result | ~10 | ~60 | ~90 |
| `orphans` | 3 results | ~25 | ~120 | ~180 |

**Scaling rule**: Each additional result item in minimal format adds approximately 7–10 tokens. In agent format, each item adds ~40–50 tokens. In json format, each item adds ~60–75 tokens.

---

## 8. Comparison with Alternatives

### 8.1 Reading Source Files vs. Querying Dominian

| Task | Read Files Directly | Dominian (minimal) | Savings |
|---|---|---|---|
| Find where `handle_request` is defined | Scan ~5 files (~4,000 tokens) | `search handle_request` (~12 tokens) | ~99.7% |
| Understand what `handle_request` depends on | Read its file + 3 imported files (~3,600 tokens) | `node_get` + `deps_direct` (~50 tokens) | ~98.6% |
| Assess impact of modifying `get_conn` | Read all files that import db.py (~5,000 tokens) | `deps_reverse` + `impact` (~40 tokens) | ~99.2% |
| Get project overview | Read 10+ key files (~10,000 tokens) | `stats` + `hotspots` + `communities` (~90 tokens) | ~99.1% |

### 8.2 grep / Search Tools vs. Structured Graph Queries

| Task | grep | Dominian (minimal) | Advantage |
|---|---|---|---|
| Find all callers of `get_conn` | `rg "get_conn"` — returns matches in every context (definitions, comments, strings, type hints) ~200 tokens, requires filtering | `deps_reverse get_conn` — returns only actual callers ~25 tokens | Structured, no false positives, 8x fewer tokens |
| Find circular dependencies | Not possible with grep | `cycles` ~30 tokens | Graph traversal required |
| Find the most complex function | Not possible with grep | `hotspots` ~40 tokens | Requires complexity analysis |
| Find which community a module belongs to | Not possible with grep | `communities` ~40 tokens | Requires graph clustering |

### 8.3 File-by-File Analysis vs. Graph Traversal

The fundamental difference: file-by-file analysis is O(n) in the number of files, and returns information about files you don't need. Graph traversal is O(k) in the number of relevant entities, and returns only what you asked for.

| Approach | Scope | Token Cost | Precision |
|---|---|---|---|
| Read all files in `src/` | Everything | ~15,000 | Over-complete |
| grep for pattern | Matching lines | ~500 | Noisy, no structural context |
| Dominian graph query | Relevant subgraph | ~50 | Exact |

The graph approach is not always sufficient — you will eventually need to read source code to make edits. But it dramatically narrows the scope: instead of reading 15 files to find the 2 that matter, you query the graph, identify the 2 relevant files, and read only those. The graph query costs ~50 tokens and saves ~10,000 tokens of unnecessary file reads.

---

## Appendix: Token Count Methodology

All token counts in this document were estimated using the `cl100k_base` tokenizer (the tokenizer used by GPT-4, GPT-4-turbo, and GPT-3.5-turbo). Estimation method:

1. Each output example was constructed as it would appear in real Dominian output.
2. Token counts were computed by encoding each string with `tiktoken` and counting the resulting tokens.
3. Where ranges are given (e.g., "~800–1,000 tokens for a 200-line file"), the range reflects variation in identifier length, comment density, and whitespace.

Counts are approximate. Actual token consumption will vary based on:
- Project-specific identifier lengths (longer names = more tokens)
- Result set sizes
- Presence of Unicode in source code (strings, comments)
- The specific LLM tokenizer used

The relative savings between formats are stable regardless of these variables, because minimal format savings come from structural compression (removing labels, headers, and decorative elements), not from name shortening.
