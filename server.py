"""
Dominian MCP Server — Model Context Protocol interface for Dominian Code Intelligence.

Exposes all Dominian CLI commands as MCP tools with minimal-format output,
optimized for LLM agent consumption (~85% token reduction vs verbose format).

Usage:
    python server.py                          # stdio transport (default)
    python server.py --transport sse --port 8080  # SSE transport

Environment:
    DOMINIAN_DB       — Path to the Dominian SQLite database (default: .dominian/agentgraph.db)
    DOMINIAN_ROOT     — Project root path (default: current working directory)
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── MCP SDK ──────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

# ── Dominian imports ────────────────────────────────────────────────
# Add the Dominian package directory to sys.path so imports work
# regardless of where the MCP server is launched from.
_DOMINIAN_SRC = os.environ.get(
    "DOMINIAN_SRC",
    os.path.dirname(os.path.abspath(__file__)),
)
if _DOMINIAN_SRC not in sys.path:
    sys.path.insert(0, _DOMINIAN_SRC)

from database import GraphDatabase
from formatter import format_minimal, format_for_claude, format_json, OutputFormat

# Optional heavy imports — may not be available in all environments
try:
    from adaptive_scanner import AdaptiveScanner
except ImportError:
    AdaptiveScanner = None

try:
    from engine import QueryEngine
except ImportError:
    QueryEngine = None


# ── Constants ────────────────────────────────────────────────────────
VERSION = "1.0.7"
DB_PATH = os.environ.get("DOMINIAN_DB", ".dominian/agentgraph.db")
PROJECT_ROOT = os.environ.get("DOMINIAN_ROOT", os.getcwd())


# ── MCP Server ──────────────────────────────────────────────────────
mcp = FastMCP(
    "dominian",
    instructions=(
        "Dominian Code Intelligence v1.0.7 — scan codebases, query dependency graphs, "
        "detect cycles, find hotspots, analyze impact, and assess refactoring safety. "
        "All output is in minimal format for optimal LLM token efficiency. "
        "Workflow: init → scan → query. Use minimal format for all tool calls."
    ),
)


# ── Helpers ─────────────────────────────────────────────────────────

def _get_db(db_path: str | None = None) -> GraphDatabase:
    """Open a database connection (caller is responsible for closing)."""
    path = db_path or DB_PATH
    return GraphDatabase(path)


def _minimal(data: dict, command_type: str = "general") -> str:
    """Format data using Dominian's minimal formatter."""
    return format_minimal(data, command_type=command_type)


def _db_path_arg(db_path: str | None = None) -> str:
    """Resolve database path from arg or environment."""
    return db_path or DB_PATH


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Project Lifecycle
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_init(
    db_path: str | None = None,
) -> str:
    """Initialize a new Dominian project and create the database.

    Creates the database directory and an empty SQLite database.
    Run this once before scanning.

    Args:
        db_path: Custom database path (default: .dominian/agentgraph.db)

    Returns:
        Minimal status string confirming initialization.
    """
    path = db_path or DB_PATH
    db_dir = os.path.dirname(path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    db = GraphDatabase(path)
    db.close()

    return f"✓ init {db_dir or '.'} db:{path}"


@mcp.tool()
def dominian_scan(
    path: str | None = None,
    db_path: str | None = None,
    mode: str = "auto",
    workers: int = 4,
) -> str:
    """Scan a codebase directory and populate the graph database.

    Scans source files, extracts code entities (functions, classes, imports),
    resolves dependency edges, and stores everything in the SQLite database.
    Adaptive strategy: <50 files = sequential, 50-500 = threaded, 500+ = multiprocess.

    Args:
        path: Root directory to scan (default: current working directory)
        db_path: Custom database path (default: .dominian/agentgraph.db)
        mode: Scan mode — "auto", "sequential", "threaded", or "process"
        workers: Number of parallel workers for threaded/process modes

    Returns:
        Minimal scan summary: files scanned, nodes extracted, edges resolved, duration.
    """
    if AdaptiveScanner is None:
        return "ERR:adaptive_scanner not available — install Dominian with all dependencies"

    root = path or PROJECT_ROOT
    dp = db_path or DB_PATH

    if not os.path.exists(root):
        return f"ERR:path not found: {root}"

    t0 = time.time()
    try:
        db = GraphDatabase(dp)
        scanner = AdaptiveScanner(db=db, root=root)
        result = scanner.scan(root, mode=mode, workers=workers)
        duration = time.time() - t0
        db.close()

        if result.get("status") != "ok":
            return f"ERR:scan failed — {result.get('status', 'unknown')}"

        return (
            f"✓ scan {result['files']}f {result['nodes']}n {result['edges']}e "
            f"{duration:.1f}s mode:{result.get('mode', mode)}"
        )
    except Exception as e:
        return f"ERR:scan failed — {e}"


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Search & Lookup
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_search(
    query: str,
    db_path: str | None = None,
) -> str:
    """Search for code entities by name, file, or signature pattern.

    Searches across all nodes in the graph database. Results are ranked
    by match quality (exact > prefix > substring) and then by code quality score.

    Args:
        query: Search term — function name, class name, file name, or partial pattern
        db_path: Custom database path

    Returns:
        Minimal search results: one-line per match with file:name:line(type) locator.
    """
    if not query:
        return "ERR:query required"

    db = _get_db(db_path)
    results = db.search_nodes(query, limit=20)
    db.close()

    data = {"results": results, "query": query}
    return _minimal(data, "search")


@mcp.tool()
def dominian_node_get(
    entity: str,
    db_path: str | None = None,
) -> str:
    """Get detailed information about a specific code entity.

    Returns the entity's type, file location, line range, complexity,
    quality score, dependency count, and dependent count.

    Args:
        entity: Name of the function, class, or module to look up
        db_path: Custom database path

    Returns:
        Minimal node detail with locator, type, complexity, quality, and connection counts.
    """
    if not entity:
        return "ERR:entity name required"

    db = _get_db(db_path)
    node = db.get_node(entity)

    if not node:
        db.close()
        return f"ERR:not found: {entity}"

    # Fetch deps/used_by counts for richer output
    deps = db.get_dependencies(entity)
    all_dependents = db.get_dependents(entity)
    real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]
    db.close()

    data = {
        "node": node,
        "deps_count": len(deps),
        "used_by_count": len(real_dependents),
    }
    return _minimal(data, "node")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Dependency Analysis
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_deps_direct(
    entity: str,
    db_path: str | None = None,
) -> str:
    """Show direct dependencies (outgoing edges) of a code entity.

    Returns everything this entity depends on: imports, function calls,
    class usage, and other relationships. If the entity has no direct
    import edges, falls back to the module-level imports for the same file.

    Args:
        entity: Name of the function, class, or module
        db_path: Custom database path

    Returns:
        Minimal dependency list: entity→dep1 | dep2 | dep3 format.
    """
    if not entity:
        return "ERR:entity name required"

    db = _get_db(db_path)
    deps = db.get_dependencies(entity)
    node = db.get_node(entity)
    db.close()

    data = {"focus": node, "dependencies": deps}
    return _minimal(data, "dependencies")


@mcp.tool()
def dominian_deps_reverse(
    entity: str,
    db_path: str | None = None,
) -> str:
    """Show reverse dependencies (incoming edges) of a code entity.

    Returns everything that depends on this entity — who calls it, who
    imports it, who uses it. Filters out 'defines' containment edges
    (parent→child) to focus on actual usage dependencies.

    Args:
        entity: Name of the function, class, or module
        db_path: Custom database path

    Returns:
        Minimal dependent list: entity←user1 | user2 format.
    """
    if not entity:
        return "ERR:entity name required"

    db = _get_db(db_path)
    all_dependents = db.get_dependents(entity)
    node = db.get_node(entity)
    db.close()

    # Filter out "defines" edges (parent-child containment, not usage)
    real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]

    data = {"focus": node, "dependents": real_dependents}
    return _minimal(data, "dependents")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Architecture Analysis
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_arch_impact(
    entity: str,
    db_path: str | None = None,
    depth: int = 10,
) -> str:
    """Analyze the blast radius of changing a code entity.

    Performs transitive dependency analysis up to the specified depth.
    Returns all nodes that would be affected by a change to this entity,
    sorted by complexity (highest first), with a risk level assessment.

    Risk levels: LOW (0-2 affected), MEDIUM (3-5), HIGH (6-10), CRITICAL (10+).

    Args:
        entity: Name of the function, class, or module to analyze
        db_path: Custom database path
        depth: Maximum traversal depth for transitive dependencies (default: 10)

    Returns:
        Minimal impact summary: risk_level count:affected1,affected2,...
    """
    if not entity:
        return "ERR:entity name required"

    db = _get_db(db_path)
    result = db.get_impact(entity, depth=depth, min_weight=0.0)
    db.close()

    return _minimal(result, "impact")


@mcp.tool()
def dominian_arch_communities(
    db_path: str | None = None,
) -> str:
    """Detect code communities using Louvain modularity algorithm.

    Groups code entities into clusters based on their connection patterns.
    Communities represent logical modules or cohesive code groups that
    should probably be in the same package/directory.

    Requires: networkx and python-louvain packages.

    Args:
        db_path: Custom database path

    Returns:
        Minimal community list: [count] [size1,size2,...] avg:average_size
    """
    dp = db_path or DB_PATH

    try:
        import networkx as nx
        import community as community_louvain
    except ImportError:
        return "ERR:requires networkx and python-louvain — pip install networkx python-louvain"

    db = GraphDatabase(dp)
    stats = db.get_stats()
    if stats.get("nodes", 0) == 0:
        db.close()
        return "ERR:database empty — run dominian_scan first"

    # Build graph
    G = nx.Graph()
    nodes = db._get_conn().execute("SELECT id, name, type, file FROM nodes").fetchall()
    for n in nodes:
        G.add_node(n[0], name=n[1], type=n[2], file=n[3])

    edges = db._get_conn().execute("SELECT from_node, to_node FROM edges").fetchall()
    for e in edges:
        if e[0] in G.nodes and e[1] in G.nodes:
            G.add_edge(e[0], e[1])

    # Detect communities
    partition = community_louvain.best_partition(G)
    communities: dict[int, list] = {}
    for node_id, comm_id in partition.items():
        communities.setdefault(comm_id, []).append(node_id)

    comm_list = []
    for cid, member_ids in sorted(communities.items(), key=lambda x: len(x[1]), reverse=True):
        members = []
        for node_id in member_ids:
            if node_id in G.nodes:
                nd = G.nodes[node_id]
                members.append({
                    "name": nd.get("name", "unknown"),
                    "type": nd.get("type", "?"),
                    "file": nd.get("file", "unknown"),
                })
        comm_list.append({"id": cid, "size": len(members), "name": f"Cluster_{cid}", "nodes": members})

    db.close()
    data = {"communities": comm_list}
    return _minimal(data, "communities")


@mcp.tool()
def dominian_arch_cross_community(
    db_path: str | None = None,
) -> str:
    """Find cross-community dependency edges — architectural boundary violations.

    Identifies dependencies that cross community boundaries. These represent
    coupling between logically separate modules and are prime candidates for
    refactoring to improve modularity.

    Requires: networkx and python-louvain packages.

    Args:
        db_path: Custom database path

    Returns:
        Minimal cross-community edges: from_file:from→to_file:to pairs.
    """
    dp = db_path or DB_PATH

    try:
        import networkx as nx
        import community as community_louvain
    except ImportError:
        return "ERR:requires networkx and python-louvain — pip install networkx python-louvain"

    db = GraphDatabase(dp)
    G = nx.Graph()
    nodes = db._get_conn().execute("SELECT id, name, type, file FROM nodes").fetchall()
    for n in nodes:
        G.add_node(n[0], name=n[1], type=n[2], file=n[3])

    edges = db._get_conn().execute("SELECT from_node, to_node FROM edges").fetchall()
    for e in edges:
        if e[0] in G.nodes and e[1] in G.nodes:
            G.add_edge(e[0], e[1])

    partition = community_louvain.best_partition(G)

    cross_edges = []
    for u, v in G.edges():
        if partition.get(u) != partition.get(v):
            u_data = G.nodes[u]
            v_data = G.nodes[v]
            cross_edges.append({
                "from": u_data["name"],
                "to": v_data["name"],
                "from_file": u_data["file"],
                "to_file": v_data["file"],
            })

    db.close()
    data = {"cross_community_edges": cross_edges[:20]}
    return _minimal(data, "cross_community")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Graph Analysis
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_graph_stats(
    db_path: str | None = None,
) -> str:
    """Get graph database statistics — node count, edge count, quality, complexity.

    Returns aggregate metrics: total nodes and edges, average quality score,
    average complexity, language distribution, and node type distribution.

    Args:
        db_path: Custom database path

    Returns:
        Minimal stats: nodes edges q:quality top_language
    """
    db = _get_db(db_path)
    stats = db.get_stats()
    db.close()

    return _minimal(stats, "stats")


@mcp.tool()
def dominian_graph_hotspots(
    limit: int = 10,
    db_path: str | None = None,
) -> str:
    """Find complexity hotspots — the most complex and poorly-connected code entities.

    Ranks nodes by a composite score of complexity, connection count, and
    inverse quality. These are the entities most likely to contain bugs
    and most difficult to maintain.

    Args:
        limit: Maximum number of hotspots to return (default: 10)
        db_path: Custom database path

    Returns:
        Minimal hotspot list: file:name:line(type) c:complexity q:quality
    """
    db = _get_db(db_path)
    hotspots = db.get_hotspots(limit)
    db.close()

    data = {"hotspots": hotspots}
    return _minimal(data, "hotspots")


@mcp.tool()
def dominian_graph_cycles(
    db_path: str | None = None,
) -> str:
    """Detect circular dependencies in the codebase.

    Finds all cycles in the dependency graph using DFS traversal.
    Circular dependencies cause initialization order problems, tight coupling,
    and make testing difficult. Each cycle is deduplicated and self-loops
    are filtered out.

    Args:
        db_path: Custom database path

    Returns:
        Minimal cycle list: count:cycle1,cycle2,...
    """
    db = _get_db(db_path)
    cycles = db.find_cycles()
    db.close()

    data = {"cycles": cycles}
    return _minimal(data, "cycles")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Refactoring Support
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_refactor_safe(
    entity: str,
    db_path: str | None = None,
) -> str:
    """Check if a code entity is safe to refactor.

    Determines refactoring safety by checking how many other entities
    depend on this one. If nothing depends on it, it's safe to modify.
    Otherwise, lists the direct dependents that would be affected.

    'defines' edges (parent→child containment) are excluded — only
    actual usage dependencies (calls, imports, uses) are counted.

    Args:
        entity: Name of the function, class, or module to check
        db_path: Custom database path

    Returns:
        Minimal safety verdict: SAFE entity or entity direct_count total_count dependents
    """
    if not entity:
        return "ERR:entity name required"

    db = _get_db(db_path)
    all_dependents = db.get_dependents(entity)
    node = db.get_node(entity)
    db.close()

    real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]
    is_safe = len(real_dependents) == 0

    data = {
        "entity": entity,
        "safe": is_safe,
        "dependents_count": len(real_dependents),
        "all_dependents_count": len(all_dependents),
        "dependents": real_dependents,
    }
    return _minimal(data, "refactor")


@mcp.tool()
def dominian_refactor_impact(
    entity: str,
    db_path: str | None = None,
) -> str:
    """Analyze the impact of refactoring a code entity.

    Alias for dominian_arch_impact — performs transitive dependency
    analysis to show the full blast radius of changing this entity.

    Args:
        entity: Name of the function, class, or module
        db_path: Custom database path

    Returns:
        Minimal impact summary: risk_level count:affected1,affected2,...
    """
    return dominian_arch_impact(entity=entity, db_path=db_path)


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — File-Level Analysis
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_file_functions(
    file: str,
    db_path: str | None = None,
) -> str:
    """List all functions and methods defined in a file.

    Returns function names extracted from the graph database for the
    specified file path. Supports partial file path matching.

    Args:
        file: File path (full or partial, e.g., 'src/main.py' or 'main.py')
        db_path: Custom database path

    Returns:
        Minimal function list: file count:fn name1,name2,...
    """
    if not file:
        return "ERR:file path required"

    db = _get_db(db_path)
    nodes = db.get_nodes_by_file(file)
    functions = [n for n in nodes if n.get("type") in ("function", "method")]
    db.close()

    data = {"file": file, "functions": functions}
    return _minimal(data, "file_functions")


@mcp.tool()
def dominian_file_classes(
    file: str,
    db_path: str | None = None,
) -> str:
    """List all classes defined in a file.

    Returns class names extracted from the graph database for the
    specified file path. Supports partial file path matching.

    Args:
        file: File path (full or partial, e.g., 'src/models.py' or 'models.py')
        db_path: Custom database path

    Returns:
        Minimal class list: file count:cls name1,name2,...
    """
    if not file:
        return "ERR:file path required"

    db = _get_db(db_path)
    nodes = db.get_nodes_by_file(file)
    classes = [n for n in nodes if n.get("type") == "class"]
    db.close()

    data = {"file": file, "classes": classes}
    return _minimal(data, "file_classes")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Project Info
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_info(
    db_path: str | None = None,
) -> str:
    """Get project status and database statistics.

    Shows whether the project is initialized, the database path,
    and the same statistics as dominian_graph_stats.

    Args:
        db_path: Custom database path

    Returns:
        Minimal stats summary.
    """
    dp = db_path or DB_PATH

    if not os.path.exists(dp):
        return "ERR:not initialized — run dominian_init first"

    db = GraphDatabase(dp)
    stats = db.get_stats()
    db.close()

    return _minimal(stats, "stats")


# ════════════════════════════════════════════════════════════════════
#  MCP TOOLS — Advanced Database Queries
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def dominian_nodes_by_type(
    type: str,
    limit: int = 25,
    db_path: str | None = None,
) -> str:
    """Get all code entities of a specific type.

    Useful for getting an overview of all functions, classes, modules,
    or variables in the codebase.

    Args:
        type: Node type — "function", "method", "class", "module", "variable", "import", "dependency"
        limit: Maximum number of results (default: 25)
        db_path: Custom database path

    Returns:
        Minimal list of nodes matching the type.
    """
    if not type:
        return "ERR:type required"

    db = _get_db(db_path)
    nodes = db.get_nodes_by_type(type, limit=limit)
    db.close()

    data = {"items": nodes}
    return _minimal(data, type)


@mcp.tool()
def dominian_nodes_by_quality(
    quality: str = "low",
    limit: int = 15,
    db_path: str | None = None,
) -> str:
    """Find low-quality or high-quality code entities.

    Low quality nodes (quality < 70) are prime refactoring candidates.
    High quality nodes (quality >= 70) represent well-structured code.

    Args:
        quality: "low" for quality < 70, "high" for quality >= 70
        limit: Maximum number of results (default: 15)
        db_path: Custom database path

    Returns:
        Minimal quality-ranked node list.
    """
    db = _get_db(db_path)
    nodes = db.get_nodes_by_quality(quality, limit)
    db.close()

    data = {"items": nodes}
    return _minimal(data, "low_quality" if quality == "low" else "high_quality")


@mcp.tool()
def dominian_god_nodes(
    limit: int = 10,
    db_path: str | None = None,
) -> str:
    """Find highly-connected 'God Object' nodes — entities that wire everything together.

    Returns nodes with the highest total degree (in + out connections).
    These are typically classes or modules that have too many responsibilities
    and should be split up.

    Args:
        limit: Maximum number of results (default: 10)
        db_path: Custom database path

    Returns:
        Minimal god-node list with connection counts.
    """
    db = _get_db(db_path)
    nodes = db.find_god_nodes(limit)
    db.close()

    data = {"items": nodes}
    return _minimal(data, "god_nodes")


@mcp.tool()
def dominian_orphans(
    db_path: str | None = None,
) -> str:
    """Find orphan nodes — code entities with no connections at all.

    Orphan nodes have no incoming or outgoing edges. They may be dead code,
    unused utilities, or recently added code that hasn't been integrated yet.

    Args:
        db_path: Custom database path

    Returns:
        Minimal orphan list.
    """
    db = _get_db(db_path)
    nodes = db.get_orphans()
    db.close()

    data = {"items": nodes}
    return _minimal(data, "orphans")


@mcp.tool()
def dominian_surprising_connections(
    db_path: str | None = None,
) -> str:
    """Find surprising cross-directory connections — hidden coupling.

    Returns edges between nodes in different top-level directories,
    excluding standard imports and defines. These represent unexpected
    coupling that may indicate architecture violations.

    Args:
        db_path: Custom database path

    Returns:
        Minimal list of surprising connections.
    """
    db = _get_db(db_path)
    connections = db.find_surprising_connections()
    db.close()

    data = {"items": connections}
    return _minimal(data, "general")


# ════════════════════════════════════════════════════════════════════
#  MCP RESOURCES
# ════════════════════════════════════════════════════════════════════

@mcp.resource("dominian://status")
def get_status() -> str:
    """Current Dominian project status — database path, node/edge counts."""
    dp = DB_PATH
    if not os.path.exists(dp):
        return "Status: Not initialized. Run dominian_init first."

    db = GraphDatabase(dp)
    stats = db.get_stats()
    db.close()

    return _minimal(stats, "stats")


@mcp.resource("dominian://schema")
def get_schema() -> str:
    """Database schema information — tables and their columns."""
    return """Dominian Graph Database Schema:

nodes: id, name, type, file, language, line_start, line_end,
       complexity, quality, signature, docstring, metadata,
       confidence, provenance, community, created_at, updated_at

edges: id, from_node, to_node, relationship, weight,
       confidence, provenance, metadata, created_at

Node types: function, method, class, module, variable, import, dependency
Edge types: imports, depends_on, uses, calls, defines, inherits, implements"""


# ════════════════════════════════════════════════════════════════════
#  MCP PROMPTS
# ════════════════════════════════════════════════════════════════════

@mcp.prompt()
def code_review(entity: str) -> str:
    """Generate a code review prompt for a specific entity."""
    return f"""Review the code entity '{entity}' using Dominian code intelligence.

Step 1: Get entity details
  → dominian_node_get(entity="{entity}")

Step 2: Check what it depends on
  → dominian_deps_direct(entity="{entity}")

Step 3: Check who depends on it
  → dominian_deps_reverse(entity="{entity}")

Step 4: Assess refactoring safety
  → dominian_refactor_safe(entity="{entity}")

Step 5: Analyze impact if changed
  → dominian_arch_impact(entity="{entity}")

Based on the results, provide:
1. Quality assessment (based on complexity and quality scores)
2. Dependency health (too many deps = fragile)
3. Coupling analysis (too many dependents = risky to change)
4. Specific refactoring recommendations
5. Risk level for any proposed changes"""


@mcp.prompt()
def architecture_review() -> str:
    """Generate an architecture review prompt for the entire codebase."""
    return """Perform a comprehensive architecture review using Dominian code intelligence.

Step 1: Get overall stats
  → dominian_graph_stats()

Step 2: Find complexity hotspots
  → dominian_graph_hotspots(limit=15)

Step 3: Detect circular dependencies
  → dominian_graph_cycles()

Step 4: Identify community structure
  → dominian_arch_communities()

Step 5: Find cross-community coupling
  → dominian_arch_cross_community()

Step 6: Find God Objects
  → dominian_god_nodes(limit=10)

Step 7: Find orphan code
  → dominian_orphans()

Step 8: Find hidden coupling
  → dominian_surprising_connections()

Based on the results, provide:
1. Overall architecture health score (1-10)
2. Top 3 architectural issues
3. Modularity assessment (community structure quality)
4. Coupling hotspots (cross-community edges)
5. Dead code / orphan analysis
6. Specific refactoring priorities ranked by impact"""


@mcp.prompt()
def refactor_plan(entity: str) -> str:
    """Generate a refactoring plan for a specific entity."""
    return f"""Create a detailed refactoring plan for '{entity}' using Dominian code intelligence.

Step 1: Check refactoring safety
  → dominian_refactor_safe(entity="{entity}")

Step 2: Analyze full impact
  → dominian_arch_impact(entity="{entity}")

Step 3: Understand dependencies
  → dominian_deps_direct(entity="{entity}")

Step 4: Map all dependents
  → dominian_deps_reverse(entity="{entity}")

Step 5: Get entity details
  → dominian_node_get(entity="{entity}")

Based on the results, provide:
1. Safety verdict: SAFE / RISKY / DANGEROUS
2. Affected entities and their risk levels
3. Step-by-step refactoring plan
4. Test coverage recommendations
5. Rollback strategy if things go wrong"""


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Dominian MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
