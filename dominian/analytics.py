"""
AgentGraph Intelligence - Graph Analytics
Community detection, god nodes, surprising connections, markdown reports.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional


class GraphAnalytics:
    """
    Advanced graph analytics. Requires networkx.
    Falls back gracefully if networkx not installed.
    """

    def __init__(self, db):
        self.db = db

    def _get_nx_graph(self):
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("Install networkx: pip install networkx")

        conn = self.db._get_conn()
        G = nx.Graph()

        for row in conn.execute("SELECT id, name, type, file, complexity, quality FROM nodes").fetchall():
            G.add_node(row[0], name=row[1], type=row[2], file=row[3],
                       complexity=row[4], quality=row[5])

        for row in conn.execute("SELECT from_node, to_node, relationship, weight FROM edges").fetchall():
            G.add_edge(row[0], row[1], relationship=row[2], weight=row[3])

        return G

    def detect_communities(self) -> Dict[str, int]:
        """
        Community detection via Louvain (python-louvain) if available,
        otherwise falls back to connected components.
        """
        G = self._get_nx_graph()
        if G.number_of_nodes() == 0:
            return {}

        try:
            import community as community_louvain
            return community_louvain.best_partition(G)
        except ImportError:
            pass

        try:
            import networkx as nx
            # Greedy modularity as second fallback
            communities = nx.community.greedy_modularity_communities(G)
            return {node: i for i, comm in enumerate(communities) for node in comm}
        except Exception:
            pass

        # Last resort: connected components
        import networkx as nx
        return {
            node: i
            for i, comp in enumerate(nx.connected_components(G))
            for node in comp
        }

    def find_god_nodes_nx(self, limit: int = 10) -> List[Dict[str, Any]]:
        """God nodes via NetworkX degree centrality."""
        G = self._get_nx_graph()
        if G.number_of_nodes() == 0:
            return []

        degrees = dict(G.degree())
        top = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:limit * 2]

        results = []
        for node_id, degree in top:
            data = G.nodes.get(node_id, {})
            if data.get("type") in ("dependency", "module"):
                continue
            results.append({
                "id":         node_id,
                "name":       data.get("name", node_id),
                "type":       data.get("type", "unknown"),
                "file":       data.get("file", ""),
                "degree":     degree,
                "complexity": data.get("complexity", 0),
                "quality":    data.get("quality", 100.0),
            })
            if len(results) >= limit:
                break
        return results

    def find_cross_community_edges(self) -> List[Dict[str, Any]]:
        """Find edges that bridge different communities — architectural surprises."""
        G = self._get_nx_graph()
        if G.number_of_nodes() == 0:
            return []

        communities = self.detect_communities()
        results = []

        for from_id, to_id, data in G.edges(data=True):
            fc = communities.get(from_id, -1)
            tc = communities.get(to_id, -1)
            if fc != tc and fc != -1 and tc != -1:
                fn = G.nodes.get(from_id, {})
                tn = G.nodes.get(to_id, {})
                results.append({
                    "from":             fn.get("name", from_id),
                    "from_file":        fn.get("file", ""),
                    "from_community":   fc,
                    "to":               tn.get("name", to_id),
                    "to_file":          tn.get("file", ""),
                    "to_community":     tc,
                    "relationship":     data.get("relationship", ""),
                    "weight":           data.get("weight", 1.0),
                })

        return sorted(results, key=lambda x: x["weight"], reverse=True)[:20]


class MarkdownReporter:
    """Generate Graphify-style markdown reports."""

    def __init__(self, db):
        self.db = db
        self.analytics = GraphAnalytics(db)

    def generate(self, output_path: str = "GRAPH_REPORT.md") -> str:
        stats    = self.db.get_stats()
        hotspots = self.db.get_hotspots(10)
        cycles   = self.db.find_cycles()
        god_db   = self.db.find_god_nodes(10)
        orphans  = self.db.get_orphans()

        try:
            god_nodes    = self.analytics.find_god_nodes_nx(10)
            communities  = self.analytics.detect_communities()
            cross_edges  = self.analytics.find_cross_community_edges()
            num_comms    = len(set(communities.values()))
        except Exception:
            god_nodes, communities, cross_edges, num_comms = god_db, {}, [], 0

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "# AgentGraph Knowledge Report",
            f"\nGenerated: {ts}",
            "\n## Summary",
            f"- **Total Nodes**: {stats['nodes']}",
            f"- **Total Edges**: {stats['edges']}",
            f"- **Languages**: {', '.join(stats.get('languages', {}).keys())}",
            f"- **Communities**: {num_comms}",
            f"- **Circular Dependencies**: {len(cycles)}",
            f"- **Orphaned Nodes**: {len(orphans)}",
            f"- **Avg Quality**: {stats['avg_quality']}%",
            f"- **Avg Complexity**: {stats['avg_complexity']}",
        ]

        conf = stats.get("confidence_distribution", {})
        if conf:
            lines += ["\n### Confidence Distribution"]
            for label, count in conf.items():
                lines.append(f"- **{label}**: {count} nodes")

        # God Nodes
        lines += [
            "\n## God Nodes (Highest Connectivity)",
            "Nodes with the most connections — likely your core abstractions.\n",
            "| Node | Type | File | Degree | Complexity | Quality |",
            "|------|------|------|--------|------------|---------|",
        ]
        for n in (god_nodes or god_db)[:10]:
            deg = n.get("degree") or n.get("total_degree", "?")
            lines.append(
                f"| {n['name']} | {n.get('type','?')} | {n.get('file','')} "
                f"| {deg} | {n.get('complexity',0)} | {n.get('quality',100):.1f}% |"
            )

        # Circular Dependencies
        lines += ["\n## Circular Dependencies"]
        if cycles:
            lines.append(f"**{len(cycles)} cycle(s) detected** — these need fixing.\n")
            for i, cycle in enumerate(cycles[:10], 1):
                lines.append(f"{i}. `{'→'.join(cycle)}`")
        else:
            lines.append("✅ No circular dependencies detected.")

        # Cross-community edges
        if cross_edges:
            lines += [
                "\n## Surprising Connections",
                "Edges crossing community boundaries — investigate these.\n",
                "| From | To | Relationship | Weight |",
                "|------|----|-------------|--------|",
            ]
            for e in cross_edges[:10]:
                lines.append(
                    f"| {e['from']} (c{e['from_community']}) "
                    f"| {e['to']} (c{e['to_community']}) "
                    f"| {e['relationship']} | {e['weight']} |"
                )

        # Hotspots
        lines += [
            "\n## Complexity Hotspots",
            "Highest risk nodes — prioritize refactoring here.\n",
            "| Node | Type | File | Complexity | Quality |",
            "|------|------|------|------------|---------|",
        ]
        for h in hotspots[:10]:
            lines.append(
                f"| {h['name']} | {h['type']} | {h['file']} "
                f"| {h['complexity']} | {h['quality']:.1f}% |"
            )

        # Low quality
        low_q = [n for n in hotspots if n.get("quality", 100) < 70]
        lines += ["\n## Quality Hotspots (< 70%)"]
        if low_q:
            for n in low_q:
                lines.append(f"- **{n['name']}** `{n['file']}`: {n['quality']:.1f}% quality, complexity {n['complexity']}")
        else:
            lines.append("✅ No low-quality nodes detected.")

        # Suggested queries
        lines += [
            "\n## Suggested Queries",
            "```",
            "python main.py query 'what are the most complex files'",
            "python main.py query 'find circular dependencies'",
            "python main.py query 'show orphaned code'",
            "python main.py query 'what breaks if I change <god_node>'",
            "```",
        ]

        report = "\n".join(lines)
        with open(output_path, "w") as f:
            f.write(report)
        return output_path