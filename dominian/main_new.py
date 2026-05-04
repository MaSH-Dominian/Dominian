"""
Dominian v1.0.7 - Strict CLI Structure
dominian <group> <action> [target] [options]

Centralized Formatting: All output delegated to formatter.py
No NLP, No Intent Classifier, No Enhanced Server required.
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

# Local imports
from .database import GraphDatabase
from .__init__ import GraphDatabase, CodebaseScanner
from .adaptive_scanner import AdaptiveScanner
from .engine import QueryEngine
from .formatter import format_for_claude, format_json, format_minimal, OutputFormat

# Constants
VERSION = "1.0.10"
DB_PATH = ".dominian/agentgraph.db"


def format_output(data: dict, fmt: str, command_type: str = "general") -> str:
    """Route to correct formatter based on format flag."""
    if fmt == "json":
        return json.dumps(format_json(data), indent=2)
    elif fmt == "minimal":
        return format_minimal(data, command_type=command_type)
    else:
        # agent format
        return format_for_claude(data, command_type=command_type)


def get_db_path() -> str:
    """Resolve database path from env or default."""
    return os.environ.get("DOMINIAN_DB", DB_PATH)


def ensure_db_exists(db_path: str) -> bool:
    """Check if database exists and has nodes."""
    if not os.path.exists(db_path):
        return False
    try:
        db = GraphDatabase(db_path)
        stats = db.get_stats()
        return stats.get("nodes", 0) > 0
    except Exception:
        return False


# ── Command Implementations ──────────────────────────────────────

def cmd_init(args):
    """Initialize project structure and empty database."""
    db_path = args.db_path or get_db_path()
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    
    # Create empty DB
    db = GraphDatabase(db_path)
    db.close()
    
    print(f"[OK] Initialized Dominian project at {db_dir or '.'}")
    print(f"[OK] Database created: {db_path}")
    print("Next: dominian scan . --no-watch")


def cmd_scan(args):
    """Scan codebase and populate database."""
    root_path = args.path or "."
    db_path = args.db_path or get_db_path()
    no_watch = getattr(args, "no_watch", True)
    
    if not os.path.exists(root_path):
        print(f"Error: Path '{root_path}' does not exist.")
        sys.exit(1)

    print(f"[SCAN] Starting scan of {root_path}...")
    start_time = time.time()
    
    try:
        db = GraphDatabase(db_path)
        scanner = AdaptiveScanner(db=db, root=root_path)
        result = scanner.scan(root_path)
        duration = time.time() - start_time
        
        print(f"[SCAN] Found {result['files']} files.")
        print(f"[SCAN] Extracted {result['nodes']} nodes.")
        print(f"[SCAN] Resolved {result['edges']} edges.")
        print(f"[SCAN] Scan complete in {duration:.2f}s.")
        
        if not no_watch:
            print("\n[!] File watcher not implemented in v1.0.7. Use --no-watch flag.")
        
        db.close()
    except Exception as e:
        print(f"[SCAN] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_search(args):
    """Search for nodes by name/pattern."""
    db_path = args.db_path or get_db_path()
    query = args.query
    fmt = args.format
    
    if not query:
        print("Error: Search query required.")
        sys.exit(1)
        
    db = GraphDatabase(db_path)
    results = db.search_nodes(query, limit=20)
    db.close()
    
    data = {"results": results, "query": query}
    print(format_output(data, fmt, "search"), end="")
    
    # Exit code 1 for empty results so agents can distinguish from success
    if not results:
        sys.exit(1)


def cmd_node_get(args):
    """Get details of a specific node."""
    db_path = args.db_path or get_db_path()
    entity = args.entity
    fmt = args.format
    
    db = GraphDatabase(db_path)
    node = db.get_node(entity)
    
    if not node:
        db.close()
        print(f"Error: Node '{entity}' not found.")
        sys.exit(1)
    
    # For minimal format, also fetch deps/used_by counts — agents need this
    if fmt == "minimal":
        deps = db.get_dependencies(entity)
        all_dependents = db.get_dependents(entity)
        real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]
        data = {
            "node": node,
            "deps_count": len(deps),
            "used_by_count": len(real_dependents),
        }
    else:
        data = {"node": node}
    
    db.close()
    print(format_output(data, fmt, "node"), end="")


def cmd_deps_direct(args):
    """Show direct dependencies (outgoing edges)."""
    db_path = args.db_path or get_db_path()
    entity = args.entity
    fmt = args.format
    
    db = GraphDatabase(db_path)
    deps = db.get_dependencies(entity)
    node = db.get_node(entity)
    db.close()
    
    data = {"focus": node, "dependencies": deps}
    print(format_output(data, fmt, "dependencies"), end="")


def cmd_deps_reverse(args):
    """Show reverse dependencies (incoming edges)."""
    db_path = args.db_path or get_db_path()
    entity = args.entity
    fmt = args.format
    
    db = GraphDatabase(db_path)
    all_dependents = db.get_dependents(entity)
    node = db.get_node(entity)
    db.close()
    
    # Filter out "defines" edges - these are parent-child containment, not usage
    real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]
    
    data = {"focus": node, "dependents": real_dependents}
    print(format_output(data, fmt, "dependents"), end="")


def cmd_arch_impact(args):
    """Analyze impact of changing a node."""
    db_path = args.db_path or get_db_path()
    entity = args.entity
    fmt = args.format
    
    db = GraphDatabase(db_path)
    # Use higher depth (10) to catch more transitive dependencies
    result = db.get_impact(entity, depth=10, min_weight=0.0)
    db.close()
    
    # Delegate ALL formatting to formatter.py
    print(format_output(result, fmt, "impact"), end="")


def cmd_arch_communities(args):
    """Detect communities using NetworkX Louvain."""
    db_path = args.db_path or get_db_path()
    fmt = args.format
    
    try:
        import networkx as nx
        import community as community_louvain
    except ImportError:
        print("Error: Requires 'networkx' and 'python-louvain'. Run: pip install networkx python-louvain")
        sys.exit(1)

    db = GraphDatabase(db_path)
    stats = db.get_stats()
    if stats.get("nodes", 0) == 0:
        print("Error: Database empty. Run 'dominian scan' first.")
        sys.exit(1)

    # Build Graph
    G = nx.Graph()
    nodes = db._get_conn().execute("SELECT id, name, type, file FROM nodes").fetchall()
    for n in nodes:
        G.add_node(n[0], name=n[1], type=n[2], file=n[3])
    
    edges = db._get_conn().execute("SELECT from_node, to_node FROM edges").fetchall()
    for e in edges:
        if e[0] in G.nodes and e[1] in G.nodes:
            G.add_edge(e[0], e[1])
    
    # Detect Communities
    partition = community_louvain.best_partition(G)
    communities = {}
    for node_id, comm_id in partition.items():
        if comm_id not in communities:
            communities[comm_id] = []
        communities[comm_id].append(node_id)
    
    # Format Result with node details
    comm_list = []
    for cid, member_ids in sorted(communities.items(), key=lambda x: len(x[1]), reverse=True):
        members = []
        for node_id in member_ids:
            if node_id in G.nodes:
                node_data = G.nodes[node_id]
                members.append({
                    "name": node_data.get("name", "unknown"),
                    "type": node_data.get("type", "?"),
                    "file": node_data.get("file", "unknown")
                })
        
        comm_list.append({
            "id": cid, 
            "size": len(members), 
            "name": f"Cluster_{cid}",
            "nodes": members
        })
        
    db.close()
    data = {"communities": comm_list}
    print(format_output(data, fmt, "communities"), end="")


def cmd_arch_cross_community(args):
    """Find edges between different communities."""
    db_path = args.db_path or get_db_path()
    fmt = args.format

    try:
        import networkx as nx
        import community as community_louvain
    except ImportError:
        print("Error: Requires 'networkx' and 'python-louvain'.")
        sys.exit(1)

    db = GraphDatabase(db_path)
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
                "to_file": v_data["file"]
            })
    
    db.close()
    data = {"cross_community_edges": cross_edges[:20]}  # Limit to 20
    print(format_output(data, fmt, "cross_community"), end="")


def cmd_graph_stats(args):
    """Show graph statistics."""
    db_path = args.db_path or get_db_path()
    fmt = args.format
    
    db = GraphDatabase(db_path)
    stats = db.get_stats()
    db.close()
    
    print(format_output(stats, fmt, "stats"), end="")


def cmd_graph_hotspots(args):
    """Show complexity hotspots."""
    db_path = args.db_path or get_db_path()
    limit = args.limit or 10
    fmt = args.format
    
    db = GraphDatabase(db_path)
    hotspots = db.get_hotspots(limit)
    db.close()
    
    data = {"hotspots": hotspots}
    print(format_output(data, fmt, "hotspots"), end="")


def cmd_graph_cycles(args):
    """Find circular dependencies."""
    db_path = args.db_path or get_db_path()
    fmt = args.format
    
    db = GraphDatabase(db_path)
    cycles = db.find_cycles()
    db.close()
    
    data = {"cycles": cycles}
    print(format_output(data, fmt, "cycles"), end="")


def cmd_refactor_safe(args):
    """Check if refactoring is safe."""
    db_path = args.db_path or get_db_path()
    entity = args.entity
    fmt = args.format
    
    db = GraphDatabase(db_path)
    all_dependents = db.get_dependents(entity)
    node = db.get_node(entity)
    db.close()
    
    # Filter out "defines" edges - these are parent-child containment, not usage
    real_dependents = [d for d in all_dependents if d.get("relationship") != "defines"]
    
    is_safe = len(real_dependents) == 0
    data = {
        "entity": entity,
        "safe": is_safe,
        "dependents_count": len(real_dependents),
        "all_dependents_count": len(all_dependents),
        "dependents": real_dependents,
        "message": "Safe to refactor" if is_safe else f"Warning: {len(real_dependents)} dependents found"
    }
    print(format_output(data, fmt, "refactor"), end="")


def cmd_refactor_impact(args):
    """Show impact of refactoring."""
    # Reuse impact logic
    cmd_arch_impact(args)


def cmd_file_functions(args):
    """List functions in a file."""
    db_path = args.db_path or get_db_path()
    file_path = args.file
    fmt = args.format
    
    db = GraphDatabase(db_path)
    nodes = db.get_nodes_by_file(file_path)
    functions = [n for n in nodes if n.get("type") in ("function", "method")]
    db.close()
    
    data = {"file": file_path, "functions": functions}
    print(format_output(data, fmt, "file_functions"), end="")


def cmd_file_classes(args):
    """List classes in a file."""
    db_path = args.db_path or get_db_path()
    file_path = args.file
    fmt = args.format
    
    db = GraphDatabase(db_path)
    nodes = db.get_nodes_by_file(file_path)
    classes = [n for n in nodes if n.get("type") == "class"]
    db.close()
    
    data = {"file": file_path, "classes": classes}
    print(format_output(data, fmt, "file_classes"), end="")


def cmd_info(args):
    """Show project info."""
    db_path = args.db_path or get_db_path()
    fmt = args.format
    
    if not os.path.exists(db_path):
        print("Status: Not initialized. Run 'dominian init' first.")
        return
        
    db = GraphDatabase(db_path)
    stats = db.get_stats()
    db.close()
    
    if fmt == "minimal":
        # Minimal: just the stats line, no verbose preamble
        print(format_output(stats, fmt, "stats"), end="")
    else:
        print(f"Project Status: Initialized")
        print(f"Database: {db_path}")
        print(format_output(stats, fmt, "stats"), end="")

# ── Main Entry Point ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="dominian",
        description="Dominian v1.0.7 - Code Intelligence for Agents"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Init
    p_init = subparsers.add_parser("init", help="Initialize project")
    p_init.add_argument("--db-path", help="Custom database path")
    p_init.set_defaults(func=cmd_init)
    
    # Scan
    p_scan = subparsers.add_parser("scan", help="Scan codebase")
    p_scan.add_argument("path", nargs="?", help="Path to scan")
    p_scan.add_argument("--db-path", help="Custom database path")
    p_scan.add_argument("--no-watch", action="store_true", help="Disable file watcher")
    p_scan.set_defaults(func=cmd_scan)
    
    # Search
    p_search = subparsers.add_parser("search", help="Search nodes")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--db-path", help="Custom database path")
    p_search.add_argument("--format", choices=["minimal", "agent", "json"], default="minimal")
    p_search.set_defaults(func=cmd_search)
    
    # Node Get
    p_node = subparsers.add_parser("node", help="Node operations")
    node_sub = p_node.add_subparsers(dest="action")
    
    p_get = node_sub.add_parser("get", help="Get node details")
    p_get.add_argument("entity", help="Node name")
    p_get.add_argument("--db-path", help="Custom database path")
    p_get.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_get.set_defaults(func=cmd_node_get)
    
    # Alias: "show" -> "get"
    p_show = node_sub.add_parser("show", help="Get node details (alias)")
    p_show.add_argument("entity", help="Node name")
    p_show.add_argument("--db-path", help="Custom database path")
    p_show.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_show.set_defaults(func=cmd_node_get)
    
    # Deps
    p_deps = subparsers.add_parser("deps", help="Dependency analysis")
    deps_sub = p_deps.add_subparsers(dest="action")
    
    p_direct = deps_sub.add_parser("direct", help="Direct dependencies")
    p_direct.add_argument("entity", help="Node name")
    p_direct.add_argument("--db-path", help="Custom database path")
    p_direct.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_direct.set_defaults(func=cmd_deps_direct)
    
    p_reverse = deps_sub.add_parser("reverse", help="Reverse dependencies")
    p_reverse.add_argument("entity", help="Node name")
    p_reverse.add_argument("--db-path", help="Custom database path")
    p_reverse.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_reverse.set_defaults(func=cmd_deps_reverse)
    
    # Arch
    p_arch = subparsers.add_parser("arch", help="Architecture analysis")
    arch_sub = p_arch.add_subparsers(dest="action")
    
    p_impact = arch_sub.add_parser("impact", help="Impact analysis")
    p_impact.add_argument("entity", help="Node name")
    p_impact.add_argument("--db-path", help="Custom database path")
    p_impact.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_impact.set_defaults(func=cmd_arch_impact)
    
    p_comms = arch_sub.add_parser("communities", help="Detect communities")
    p_comms.add_argument("--db-path", help="Custom database path")
    p_comms.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_comms.set_defaults(func=cmd_arch_communities)
    
    p_cross = arch_sub.add_parser("cross-community", help="Cross-community edges")
    p_cross.add_argument("--db-path", help="Custom database path")
    p_cross.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_cross.set_defaults(func=cmd_arch_cross_community)
    
    # Graph
    p_graph = subparsers.add_parser("graph", help="Graph analysis")
    graph_sub = p_graph.add_subparsers(dest="action")
    
    p_stats = graph_sub.add_parser("stats", help="Graph statistics")
    p_stats.add_argument("--db-path", help="Custom database path")
    p_stats.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_stats.set_defaults(func=cmd_graph_stats)
    
    p_hot = graph_sub.add_parser("hotspots", help="Complexity hotspots")
    p_hot.add_argument("--limit", type=int, default=10)
    p_hot.add_argument("--db-path", help="Custom database path")
    p_hot.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_hot.set_defaults(func=cmd_graph_hotspots)
    
    p_cyc = graph_sub.add_parser("cycles", help="Circular dependencies")
    p_cyc.add_argument("--db-path", help="Custom database path")
    p_cyc.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_cyc.set_defaults(func=cmd_graph_cycles)
    
    # Alias: "circular" -> "cycles"
    p_circular = graph_sub.add_parser("circular", help="Circular dependencies (alias)")
    p_circular.add_argument("--db-path", help="Custom database path")
    p_circular.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_circular.set_defaults(func=cmd_graph_cycles)
    
    # Refactor
    p_ref = subparsers.add_parser("refactor", help="Refactoring support")
    ref_sub = p_ref.add_subparsers(dest="action")
    
    p_safe = ref_sub.add_parser("safe", help="Check safety")
    p_safe.add_argument("entity", help="Node name")
    p_safe.add_argument("--db-path", help="Custom database path")
    p_safe.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_safe.set_defaults(func=cmd_refactor_safe)
    
    # Alias: "safety" -> "safe"
    p_safety = ref_sub.add_parser("safety", help="Check safety (alias)")
    p_safety.add_argument("entity", help="Node name")
    p_safety.add_argument("--db-path", help="Custom database path")
    p_safety.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_safety.set_defaults(func=cmd_refactor_safe)
    
    p_imp = ref_sub.add_parser("impact", help="Refactor impact")
    p_imp.add_argument("entity", help="Node name")
    p_imp.add_argument("--db-path", help="Custom database path")
    p_imp.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_imp.set_defaults(func=cmd_refactor_impact)
    
    # File
    p_file = subparsers.add_parser("file", help="File analysis")
    file_sub = p_file.add_subparsers(dest="action")
    
    p_funcs = file_sub.add_parser("functions", help="List functions")
    p_funcs.add_argument("file", help="File path")
    p_funcs.add_argument("--db-path", help="Custom database path")
    p_funcs.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_funcs.set_defaults(func=cmd_file_functions)
    
    p_cls = file_sub.add_parser("classes", help="List classes")
    p_cls.add_argument("file", help="File path")
    p_cls.add_argument("--db-path", help="Custom database path")
    p_cls.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_cls.set_defaults(func=cmd_file_classes)
    
    # Info
    p_info = subparsers.add_parser("info", help="Project info")
    p_info.add_argument("--db-path", help="Custom database path")
    p_info.add_argument("--format", choices=["minimal", "agent", "json", "text"], default="minimal")
    p_info.set_defaults(func=cmd_info)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()