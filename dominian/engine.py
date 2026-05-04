"""
AgentGraph Intelligence - Query Engine
Resolves CLI commands against the graph database.
"""

import time
from typing import Dict, Any, List, Optional, Tuple


class QueryEngine:
    def __init__(self, db):
        self.db = db
        
    def query(self, raw: str, session_id: str = "default", limit: int = 25) -> Dict[str, Any]:
        t0 = time.perf_counter()
        raw = raw.strip()
        intent, entity = self._detect_intent(raw)
        result = self._resolve(intent, entity, limit)
        latency = (time.perf_counter() - t0) * 1000

        self.db.log_query(
            session_id=session_id, raw_query=raw,
            resolved=f"{intent}:{entity}",
            result_count=len(result.get("items", [])),
            latency_ms=round(latency, 3),
        )

        return {"query": raw, "intent": intent, "entity": entity,
                "latency_ms": round(latency, 3), **result}

    def _detect_intent(self, raw: str) -> Tuple[str, str]:
        """CLI intent detection - map CLI patterns to intents."""
        # CLI command patterns
        if "what does" in raw and "depend on" in raw:
            entity = raw.replace("what does", "").replace("depend on", "").strip()
            return "dependencies", entity
        elif "what depends on" in raw:
            entity = raw.replace("what depends on", "").strip()
            return "dependents", entity
        elif "impact of" in raw or "refactoring impact" in raw:
            # Extract entity after impact keywords
            parts = raw.split("impact of") if "impact of" in raw else raw.split("refactoring impact")
            if len(parts) > 1:
                entity = parts[1].strip()
                return "impact", entity
            return "impact", ""
        elif "safe to refactor" in raw:
            # Extract entity after "safe to refactor"
            parts = raw.split("safe to refactor")
            if len(parts) > 1:
                entity = parts[1].strip()
                return "refactoring_safety", entity
            return "refactoring_safety", ""
        elif "hotspots" in raw:
            return "hotspots", ""
        elif "cycles" in raw or "circular" in raw:
            return "cycles", ""
        elif "communities" in raw:
            return "communities", ""
        elif "stats" in raw:
            return "stats", ""
        else:
            return "node_lookup", raw

    def _resolve(self, intent: str, entity: str, limit: int) -> Dict[str, Any]:
        dispatch = {
            "dependencies": self._resolve_dependencies,
            "dependents":   self._resolve_dependents,
            "impact":       self._resolve_impact,
            "refactoring_safety": self._resolve_refactoring_safety,
            "refactoring_impact": lambda e: self._resolve_refactoring_impact(e),
            "cycles":       lambda e: self._resolve_cycles(),
            "hotspots":     lambda e: self._resolve_hotspots(),
            "low_quality":  lambda e: self._resolve_quality("low", limit),
            "high_quality": lambda e: self._resolve_quality("high", limit),
            "by_type":      lambda e: self._resolve_by_type(e, limit),
            "by_file":      self._resolve_by_file,
            "orphans":      lambda e: self._resolve_orphans(),
            "stats":        lambda e: self._resolve_stats(),
            "god_nodes":    lambda e: self._resolve_god_nodes(limit),
            "communities":  lambda e: self._resolve_communities(),
            "surprising":   lambda e: self._resolve_surprising(),
            # Enhanced community queries
            "community_nodes": lambda e: self._resolve_community_nodes(e, limit),
            "node_community": self._resolve_node_community,
            "cross_community_edges": lambda e: self._resolve_cross_community_edges(limit),
            "community_cohesion": lambda e: self._resolve_community_cohesion(),
            "weak_communities": lambda e: self._resolve_weak_communities(),
            # Advanced dependency analysis
            "transitive_dependencies": lambda e: self._resolve_transitive_dependencies(e, limit),
            "dependency_tree": lambda e: self._resolve_dependency_tree(e, limit),
            "upstream_downstream": lambda e: self._resolve_upstream_downstream(e, limit),
            # Architecture analysis
            "architecture_patterns": lambda e: self._resolve_architecture_patterns(limit),
            "layer_boundaries": lambda e: self._resolve_layer_boundaries(),
            "coupling_analysis": lambda e: self._resolve_coupling_analysis(),
            # Refactoring support
            "refactoring_operations": lambda e: self._resolve_refactoring_operations(e),
            # Performance analysis
            "performance_analysis": lambda e: self._resolve_performance_analysis(limit),
            "usage_frequency": lambda e: self._resolve_usage_frequency(limit),
            "resource_intensive": lambda e: self._resolve_resource_intensive(limit),
            # New query types
            "quantitative": self._resolve_quantitative,
            "complexity_analysis": lambda e: self._resolve_complexity_analysis(e, limit),
            "structure": self._resolve_structure,
        }
        fn = dispatch.get(intent)
        if fn:
            return fn(entity)
        return self._resolve_node_lookup(entity, limit)

    # ── Resolvers ─────────────────────────────────────────────────

    def _find_node(self, name: str) -> Optional[Dict]:
        """Find node by name or return None."""
        nodes = self.db.get_nodes_by_name(name)
        return nodes[0] if nodes else None

    def _resolve_dependencies(self, entity: str) -> Dict:
        node = self._find_node(entity)
        if not node:
            return {"items": [], "message": f"Node '{entity}' not found"}
        deps = self.db.get_dependencies(node["name"], node["file"])
        return {"focus": node, "items": deps, "count": len(deps),
                "message": f"{node['name']} depends on {len(deps)} nodes"}

    def _resolve_dependents(self, entity: str) -> Dict:
        node = self._find_node(entity)
        if not node:
            return {"items": [], "message": f"Node '{entity}' not found"}
        used_by = self.db.get_dependents(node["name"], node["file"])
        return {"focus": node, "items": used_by, "count": len(used_by),
                "message": f"{node['name']} is used by {len(used_by)} nodes"}

    def _resolve_impact(self, entity: str) -> Dict:
        node = self._find_node(entity)
        if not node:
            return {"items": [], "message": f"Node '{entity}' not found"}

        # Get all dependents (transitive)
        impact_result = self.db.get_impact(node["name"], node["file"])
        affected = impact_result.get("affected_nodes", [])
        risk_level = impact_result.get("risk_level", "LOW")
        
        return {"focus": node, "items": affected, "count": len(affected),
                "risk_level": risk_level,
                "message": f"Changing {node['name']} affects {len(affected)} nodes ({risk_level} risk)"}

    def _resolve_refactoring_safety(self, entity: str) -> Dict:
        node = self._find_node(entity)
        if not node:
            return {"items": [], "message": f"Node '{entity}' not found"}

        # Get dependents and dependencies
        deps = self.db.get_dependencies(node["name"], node["file"])
        used_by = self.db.get_dependents(node["name"], node["file"])
        
        # Calculate risk based on complexity and connections
        complexity = node.get("complexity", 0)
        total_connections = len(deps) + len(used_by)
        
        risk_factors = []
        if complexity > 10:
            risk_factors.append("high complexity")
        if total_connections > 20:
            risk_factors.append("many connections")
        
        is_safe = len(risk_factors) == 0
        
        return {"focus": node, "items": risk_factors, "count": len(risk_factors),
                "is_safe": is_safe, "risk_level": "HIGH" if not is_safe else "LOW",
                "message": f"Refactoring {node['name']} is {'high risk' if not is_safe else 'low risk'}"}

    def _resolve_refactoring_impact(self, entity: str) -> Dict:
        # Same as impact analysis
        return self._resolve_impact(entity)

    def _resolve_cycles(self) -> Dict:
        cycles = self.db.find_cycles()
        if not cycles:
            return {"items": [], "message": "No circular dependencies found"}
        
        formatted_cycles = []
        for cycle in cycles[:10]:  # Limit to 10
            formatted_cycles.append(" -> ".join(cycle))
        
        return {"items": formatted_cycles, "count": len(cycles),
                "message": f"Found {len(cycles)} circular dependencies"}

    def _resolve_hotspots(self, limit: int = 10) -> Dict:
        hotspots = self.db.get_hotspots(limit)
        return {"items": hotspots, "count": len(hotspots),
                "message": f"Top {len(hotspots)} complexity hotspots"}

    def _resolve_quality(self, quality_type: str, limit: int) -> Dict:
        nodes = self.db.get_nodes_by_quality(quality_type, limit)
        return {"items": nodes, "count": len(nodes),
                "message": f"{quality_type.title()} quality nodes"}

    def _resolve_by_type(self, type_filter: str, limit: int) -> Dict:
        nodes = self.db.get_nodes_by_type(type_filter, limit)
        return {"items": nodes, "count": len(nodes),
                "message": f"Nodes of type '{type_filter}'"}

    def _resolve_by_file(self, file_path: str) -> Dict:
        nodes = self.db.get_nodes_by_file(file_path)
        return {"items": nodes, "count": len(nodes),
                "message": f"Nodes in file '{file_path}'"}

    def _resolve_orphans(self) -> Dict:
        orphans = self.db.get_orphans()
        return {"items": orphans, "count": len(orphans),
                "message": f"Found {len(orphans)} orphan nodes"}

    def _resolve_stats(self) -> Dict:
        stats = self.db.get_stats()
        return {"stats": stats, "message": "Graph statistics"}

    def _resolve_god_nodes(self, limit: int) -> Dict:
        god_nodes = self.db.find_god_nodes(limit)
        return {"items": god_nodes, "count": len(god_nodes),
                "message": f"Top {len(god_nodes)} connected nodes"}

    def _resolve_communities(self) -> Dict:
        communities = self.db.get_communities()
        return {"items": communities, "count": len(communities),
                "message": f"Found {len(communities)} communities"}

    def _resolve_surprising(self) -> Dict:
        surprising = self.db.find_surprising_connections()
        return {"items": surprising, "count": len(surprising),
                "message": f"Found {len(surprising)} surprising connections"}

    def _resolve_node_lookup(self, entity: str, limit: int) -> Dict:
        nodes = self.db.get_nodes_by_name(entity, limit)
        return {"items": nodes, "count": len(nodes),
                "message": f"Found {len(nodes)} nodes matching '{entity}'"}

    # Enhanced resolver methods (placeholders for future implementation)
    def _resolve_community_nodes(self, community_id: str, limit: int) -> Dict:
        return {"items": [], "message": f"Community nodes for {community_id}"}

    def _resolve_node_community(self, entity: str) -> Dict:
        return {"items": [], "message": f"Community for {entity}"}

    def _resolve_cross_community_edges(self, limit: int) -> Dict:
        return {"items": [], "message": "Cross-community edges"}

    def _resolve_community_cohesion(self) -> Dict:
        return {"items": [], "message": "Community cohesion"}

    def _resolve_weak_communities(self) -> Dict:
        return {"items": [], "message": "Weak communities"}

    def _resolve_transitive_dependencies(self, entity: str, limit: int) -> Dict:
        return {"items": [], "message": f"Transitive dependencies for {entity}"}

    def _resolve_dependency_tree(self, entity: str, limit: int) -> Dict:
        return {"items": [], "message": f"Dependency tree for {entity}"}

    def _resolve_upstream_downstream(self, entity: str, limit: int) -> Dict:
        return {"items": [], "message": f"Upstream/downstream for {entity}"}

    def _resolve_architecture_patterns(self, limit: int) -> Dict:
        return {"items": [], "message": "Architecture patterns"}

    def _resolve_layer_boundaries(self) -> Dict:
        return {"items": [], "message": "Layer boundaries"}

    def _resolve_coupling_analysis(self) -> Dict:
        return {"items": [], "message": "Coupling analysis"}

    def _resolve_refactoring_operations(self, entity: str) -> Dict:
        return {"items": [], "message": f"Refactoring operations for {entity}"}

    def _resolve_performance_analysis(self, limit: int) -> Dict:
        return {"items": [], "message": "Performance analysis"}

    def _resolve_usage_frequency(self, limit: int) -> Dict:
        return {"items": [], "message": "Usage frequency"}

    def _resolve_resource_intensive(self, limit: int) -> Dict:
        return {"items": [], "message": "Resource intensive operations"}

    def _resolve_quantitative(self) -> Dict:
        return {"items": [], "message": "Quantitative analysis"}

    def _resolve_complexity_analysis(self, entity: str, limit: int) -> Dict:
        return {"items": [], "message": f"Complexity analysis for {entity}"}

    def _resolve_structure(self) -> Dict:
        return {"items": [], "message": "Structure analysis"}


# Type normalization for better search results
TYPE_NORMALIZATION = {
    "function": "function", "method": "function", "variable": "variable",
    "class": "class", "interface": "interface", "enum": "variable",
    "dependencies": "dependency", "dependency": "dependency",
}
