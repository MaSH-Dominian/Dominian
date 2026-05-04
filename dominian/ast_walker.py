"""
AgentGraph Intelligence - AST Walker
Walks tree-sitter parse trees and extracts nodes + edges in AgentGraph schema.
Implements Graphify's two-pass strategy:
  Pass 1 — structural (classes, functions, imports, interfaces)
  Pass 2 — call-graph (INFERRED call edges via S-expression queries)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .tree_sitter_configs import LanguageConfig
from .import_resolver import resolve_import_to_file


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _node_text(node, source_bytes: bytes) -> str:
    """Extract raw UTF-8 text for a tree-sitter node."""
    try:
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _child_by_field(node, field_name: str):
    """Safe child_by_field_name wrapper."""
    try:
        return node.child_by_field_name(field_name)
    except Exception:
        return None


def _child_type(node, type_name: str):
    """First child of given type."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _all_children_of_type(node, type_name: str):
    return [c for c in node.children if c.type == type_name]


def _line_range(node) -> Tuple[int, int]:
    return node.start_point[0] + 1, node.end_point[0] + 1


def _cyclomatic(node, source_bytes: bytes) -> int:
    """Approximate McCabe complexity from text — language-agnostic."""
    text = _node_text(node, source_bytes)
    hits = len(re.findall(
        r'\b(if|else|elif|for|while|switch|case|catch|&&|\|\||and\b|or\b|match\b|select\b)\b',
        text
    ))
    return min(1 + hits, 20)


def _score_quality(complexity: int, has_doc: bool, node_type: str) -> float:
    score = 100.0
    if complexity > 10:
        score -= 30
    elif complexity > 7:
        score -= 20
    elif complexity > 5:
        score -= 10
    elif complexity > 3:
        score -= 5
    if not has_doc and node_type in ("function", "method", "class"):
        score -= 10
    return max(0.0, min(100.0, score))


def _extract_doc_comment(node, source_bytes: bytes, config: LanguageConfig) -> str:
    """
    Look backwards through siblings for a leading doc comment.
    Handles: Python docstrings, Java /** */, Rust ///, Go //, C++ ///
    """
    parent = node.parent
    if parent is None:
        return ""

    prev = None
    for child in parent.children:
        if child == node:
            break
        prev = child

    if prev is None:
        return ""

    # Block comments  /** ... */ or /* ... */
    if prev.type in ("block_comment", "comment"):
        raw = _node_text(prev, source_bytes)
        raw = re.sub(r'^/\*+\s*', '', raw)
        raw = re.sub(r'\s*\*+/$', '', raw)
        raw = re.sub(r'\n\s*\*?\s?', ' ', raw)
        return raw.strip()

    # Line comments  // ... or # ...
    if prev.type in ("line_comment",):
        raw = _node_text(prev, source_bytes)
        return re.sub(r'^//+\s*', '', raw).strip()

    # Python: first child of body is expression_statement containing string
    if prev.type in ("expression_statement",):
        for gc in prev.children:
            if gc.type in ("string", "string_literal"):
                raw = _node_text(gc, source_bytes)
                return raw.strip('"""').strip("'''").strip('"').strip("'").strip()

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Import extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_python_import(node, source_bytes: bytes, rel_file: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    nodes_out, edges_out = [], []
    text = _node_text(node, source_bytes)
    lineno, _ = _line_range(node)

    if node.type == "import_statement":
        # import os, import os as o
        for name_node in node.children:
            if name_node.type in ("dotted_name", "aliased_import"):
                dep = _node_text(name_node, source_bytes).split(" as ")[0].strip()
                nodes_out.append(_dep_node(dep, rel_file, "python", lineno, f"import {dep}"))
                edges_out.append(_make_edge(module_name, rel_file, dep, rel_file, "imports", 5.0))
    else:
        # from x import y, z
        mod_node = _child_by_field(node, "module_name") or _child_type(node, "dotted_name")
        mod = _node_text(mod_node, source_bytes) if mod_node else ""
        for child in node.children:
            if child.type in ("import_from_statement",):
                continue
            if child.type in ("dotted_name", "aliased_import", "wildcard_import"):
                sym = _node_text(child, source_bytes).split(" as ")[0].strip()
                dep = f"{mod}.{sym}" if mod and sym != "*" else mod or sym
                nodes_out.append(_dep_node(dep, rel_file, "python", lineno, f"from {mod} import {sym}"))
                edges_out.append(_make_edge(module_name, rel_file, dep, rel_file, "imports", 6.0))

    return nodes_out, edges_out


def _extract_js_import(node, source_bytes: bytes, rel_file: str, lang: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    nodes_out, edges_out = [], []
    lineno, _ = _line_range(node)

    # Try field 'source' first (tree-sitter JS/TS grammar)
    src_node = _child_by_field(node, "source")
    if src_node is None:
        for child in node.children:
            if child.type in ("string", "string_literal"):
                src_node = child
                break

    if src_node is not None:
        mod_path = _node_text(src_node, source_bytes).strip("'\"")
        # Handle string_fragment child inside the string node
        for gc in src_node.children:
            if gc.type == "string_fragment":
                mod_path = _node_text(gc, source_bytes)
                break
    else:
        import re as _re
        m = _re.search(r"""['"]([^'"]+)['"]""", _node_text(node, source_bytes))
        mod_path = m.group(1) if m else _node_text(node, source_bytes)

    if not mod_path:
        return nodes_out, edges_out

    nodes_out.append(_dep_node(mod_path, rel_file, lang, lineno, f"import from '{mod_path}'"))
    edges_out.append(_make_edge(module_name, rel_file, mod_path, rel_file, "imports", 6.0))
    return nodes_out, edges_out

def _extract_java_import(node, source_bytes: bytes, rel_file: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    text = _node_text(node, source_bytes)
    dep  = re.sub(r'^import\s+(static\s+)?', '', text).rstrip(';').strip()
    lineno, _ = _line_range(node)
    return (
        [_dep_node(dep, rel_file, "java", lineno, f"import {dep}")],
        [_make_edge(module_name, rel_file, dep, rel_file, "imports", 5.0)],
    )


def _extract_go_import(node, source_bytes: bytes, rel_file: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    nodes_out, edges_out = [], []
    for child in node.children:
        if child.type in ("import_spec",):
            path_node = _child_type(child, "interpreted_string_literal") or _child_by_field(child, "path")
            if path_node:
                dep = _node_text(path_node, source_bytes).strip('"')
                lineno, _ = _line_range(child)
                nodes_out.append(_dep_node(dep, rel_file, "go", lineno, f'import "{dep}"'))
                edges_out.append(_make_edge(module_name, rel_file, dep, rel_file, "imports", 5.0))
        elif child.type == "interpreted_string_literal":
            dep = _node_text(child, source_bytes).strip('"')
            lineno, _ = _line_range(child)
            nodes_out.append(_dep_node(dep, rel_file, "go", lineno, f'import "{dep}"'))
            edges_out.append(_make_edge(module_name, rel_file, dep, rel_file, "imports", 5.0))
    return nodes_out, edges_out


def _extract_rust_use(node, source_bytes: bytes, rel_file: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    text = re.sub(r'^use\s+', '', _node_text(node, source_bytes)).rstrip(';').strip()
    lineno, _ = _line_range(node)
    return (
        [_dep_node(text, rel_file, "rust", lineno, f"use {text}")],
        [_make_edge(module_name, rel_file, text, rel_file, "imports", 5.0)],
    )


def _extract_cpp_include(node, source_bytes: bytes, rel_file: str, module_name: str) -> Tuple[List[Dict], List[Dict]]:
    text = _node_text(node, source_bytes)
    m = re.search(r'[<"]([^>"]+)[>"]', text)
    dep = m.group(1) if m else text
    lineno, _ = _line_range(node)
    return (
        [_dep_node(dep, rel_file, "cpp", lineno, f"#include <{dep}>")],
        [_make_edge(module_name, rel_file, dep, rel_file, "imports", 5.0)],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Signature builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_signature(node, source_bytes: bytes, config: LanguageConfig, sym_name: str, agtype: str) -> str:
    """Best-effort one-liner signature from AST node."""
    # Take first line of the node text (up to 160 chars)
    text = _node_text(node, source_bytes)
    first_line = text.splitlines()[0][:160] if text else sym_name
    return first_line


# ─────────────────────────────────────────────────────────────────────────────
# Node / edge factory helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dep_node(name: str, file: str, lang: str, lineno: int, sig: str) -> Dict:
    return {
        "name": name, "type": "dependency",
        "file": file, "language": lang,
        "line_start": lineno, "line_end": lineno,
        "complexity": 0, "quality": 100.0,
        "signature": sig, "docstring": "",
        "metadata": {},
        "confidence": "EXTRACTED",
        "provenance": "tree_sitter",
    }


def _make_edge(fn: str, ff: str, tn: str, tf: str, rel: str, w: float, confidence: float = 1.0, provenance: str = "tree_sitter") -> Dict:
    return {
        "from_name": fn, "from_file": ff,
        "to_name": tn, "to_file": tf,
        "relationship": rel, "weight": w,
        "confidence": confidence, "provenance": provenance,
    }


def _make_node(
    name: str, agtype: str, file: str, lang: str,
    line_start: int, line_end: int,
    complexity: int, docstring: str, signature: str,
    metadata: Dict,
) -> Dict:
    quality = _score_quality(complexity, bool(docstring), agtype)
    return {
        "name": name, "type": agtype,
        "file": file, "language": lang,
        "line_start": line_start, "line_end": line_end,
        "complexity": complexity, "quality": quality,
        "signature": signature, "docstring": docstring,
        "metadata": metadata,
        "confidence": "EXTRACTED",
        "provenance": "tree_sitter",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main walker
# ─────────────────────────────────────────────────────────────────────────────

class ASTWalker:
    """
    Language-agnostic walker that uses LanguageConfig to drive extraction.
    Implements Graphify's two-pass approach:
      _walk_structural() — pass 1, deterministic
      _walk_calls()      — pass 2, S-expression query based (INFERRED)
    """

    # Node types we skip to avoid noise
    _SKIP_TYPES: Set[str] = {
        "comment", "line_comment", "block_comment",
        "string", "string_literal", "number", "boolean",
        "ERROR", "MISSING",
        ",", ";", "(", ")", "{", "}", "[", "]", ":", ".",
    }

    def __init__(self, config: LanguageConfig, file_path: str, source_bytes: bytes, project_root: Optional[str] = None):
        self.config       = config
        self.rel_file     = file_path
        self.source_bytes = source_bytes
        self.lang         = config.name
        self.project_root = project_root or os.getcwd()

        # Scope stack: list of (name, type) tuples
        self._scope: List[Tuple[str, str]] = []

        # Collected output
        self.nodes: List[Dict] = []
        self.edges: List[Dict] = []

        # Track seen names to avoid duplicates
        self._seen_nodes: Set[str] = set()

        # Module (file stem) used as top-level owner
        self._module_name = Path(file_path).name  # e.g. "main.py" to avoid collisions

    # ── Public API ────────────────────────────────────────────────

    def walk(self, tree_root) -> Tuple[List[Dict], List[Dict]]:
        """Full two-pass walk. Returns (nodes, edges)."""
        # Module node
        total_lines = self.source_bytes.count(b"\n") + 1
        mod_node = _make_node(
            name       = self._module_name,
            agtype     = "module",
            file       = self.rel_file,
            lang       = self.lang,
            line_start = 1,
            line_end   = total_lines,
            complexity = 0,
            docstring  = "",
            signature  = f"module {self._module_name}",
            metadata   = {"language": self.lang},
        )
        self.nodes.append(mod_node)

        # Pass 1: structural
        self._scope = [(self._module_name, "module")]
        self._walk_structural(tree_root)

        # Pass 2: call-graph (requires tree-sitter Language object for queries)
        # Handled inside TreeSitterParser if ts_language is available

        return self.nodes, self.edges

    # ── Pass 1 ────────────────────────────────────────────────────

    def _walk_structural(self, node):
        ntype = node.type
        if ntype in self._SKIP_TYPES:
            return

        config = self.config
        handled = False
        is_container = False

        # ── Imports / dependencies ──
        if ntype in config.import_node_types:
            n, e = self._extract_import(node)
            self.nodes.extend(n)
            self.edges.extend(e)
            handled = True

        # ── Structural constructs ──
        elif ntype in config.node_type_map:
            agtype = config.node_type_map[ntype]
            if agtype in ("class", "interface", "function", "method", "variable"):
                is_container = self._extract_symbol(node, ntype, agtype)
                handled = is_container is not None

        # Recurse into children unless the node was already consumed as a container
        # (containers handle their own children inside _extract_symbol to maintain scope)
        if not is_container:
            for child in node.children:
                self._walk_structural(child)

    def _extract_symbol(self, node, ntype: str, agtype: str) -> bool:
        """Extract a symbol node. Returns True if node is a container (class/function/method)
        that already recursed into its children."""
        config = self.config
        src    = self.source_bytes

        # ── Resolve name ──
        name = self._resolve_name(node, ntype)
        if not name or name in self._SKIP_TYPES:
            return False

        # Qualify with enclosing class for methods
        owner_name, owner_type = self._scope[-1] if self._scope else (self._module_name, "module")
        if agtype == "method" or (agtype == "function" and owner_type == "class"):
            qual_name = f"{owner_name}.{name}"
            agtype    = "method"
        else:
            qual_name = name

        if qual_name in self._seen_nodes:
            return False
        self._seen_nodes.add(qual_name)

        # ── Lines ──
        line_start, line_end = _line_range(node)

        # ── Complexity ──
        body_field = config.body_fields.get(ntype)
        body_node  = _child_by_field(node, body_field) if body_field else node
        complexity = _cyclomatic(body_node or node, src) if agtype in ("function", "method", "class") else 0

        # ── Docstring ──
        docstring = _extract_doc_comment(node, src, config)
        # Python: also check first statement of body
        if not docstring and agtype in ("function", "method", "class") and body_node:
            for bchild in body_node.children:
                if bchild.type == "expression_statement":
                    for gc in bchild.children:
                        if gc.type == "string":
                            docstring = _node_text(gc, src).strip('"""').strip("'''").strip('"').strip("'")
                            break
                if docstring:
                    break

        # ── Signature ──
        signature = _build_signature(node, src, config, qual_name, agtype)

        # ── Metadata ──
        metadata: Dict[str, Any] = {}

        # Bases / extends / implements
        bases, ifaces = self._resolve_inheritance(node, ntype)
        if bases:
            metadata["bases"] = bases
        if ifaces:
            metadata["implements"] = ifaces

        # Params
        param_field = config.param_fields.get(ntype)
        if param_field:
            pnode = _child_by_field(node, param_field)
            if pnode:
                metadata["params"] = _node_text(pnode, src)

        # Return type
        ret_field = config.return_fields.get(ntype)
        if ret_field:
            rnode = _child_by_field(node, ret_field)
            if rnode:
                metadata["returns"] = _node_text(rnode, src)

        # Build node
        sym_node = _make_node(
            name       = qual_name,
            agtype     = agtype,
            file       = self.rel_file,
            lang       = self.lang,
            line_start = line_start,
            line_end   = line_end,
            complexity = complexity,
            docstring  = docstring,
            signature  = signature,
            metadata   = metadata,
        )
        self.nodes.append(sym_node)

        # ── Edges ──
        # defines edge from current owner
        self.edges.append(_make_edge(
            owner_name, self.rel_file, qual_name, self.rel_file,
            "defines", config.default_edge_weight("defines"),
        ))

        # inheritance edges
        for base in bases:
            self.edges.append(_make_edge(
                qual_name, self.rel_file, base, self.rel_file,
                "inherits", config.default_edge_weight("inherits"),
            ))
        for iface in ifaces:
            self.edges.append(_make_edge(
                qual_name, self.rel_file, iface, self.rel_file,
                "implements", config.default_edge_weight("implements"),
            ))

        # ── Container handling: push scope, recurse children, pop scope ──
        if agtype in ("class", "interface", "function", "method"):
            self._scope.append((qual_name, agtype))
            for child in node.children:
                self._walk_structural(child)
            self._scope.pop()
            return True  # Tell caller we already recursed into children

        return False

    # ── Name resolution ──────────────────────────────────────────

    def _resolve_name(self, node, ntype: str) -> Optional[str]:
        config = self.config
        src    = self.source_bytes

        field = config.name_fields.get(ntype)
        if field:
            child = _child_by_field(node, field)
            if child:
                return _node_text(child, src)

        # Fallbacks per language
        lang = self.lang

        if lang == "go":
            if ntype == "type_spec":
                name_child = _child_by_field(node, "name")
                if name_child:
                    return _node_text(name_child, src)
            if ntype == "function_declaration":
                name_child = _child_by_field(node, "name")
                if name_child:
                    return _node_text(name_child, src)
            if ntype == "method_declaration":
                name_child = _child_by_field(node, "name")
                if name_child:
                    return _node_text(name_child, src)

        if lang == "rust" and ntype == "impl_item":
            # impl Trait for Type  → use "Type" as the name
            type_node = _child_by_field(node, "type")
            if type_node:
                return _node_text(type_node, src)

        if lang in ("javascript", "typescript"):
            if ntype in ("lexical_declaration", "variable_declaration"):
                # const foo = ...  → find first declarator.name
                for child in node.children:
                    if child.type in ("variable_declarator",):
                        n = _child_by_field(child, "name")
                        if n:
                            return _node_text(n, src)

        if lang == "cpp":
            if ntype == "function_definition":
                decl = _child_by_field(node, "declarator")
                if decl:
                    # drill into nested declarator
                    while decl and decl.type not in ("identifier", "qualified_identifier", "operator_name"):
                        inner = _child_by_field(decl, "declarator")
                        if inner:
                            decl = inner
                        else:
                            break
                    if decl:
                        return _node_text(decl, src).split("(")[0].split("::")[-1].strip()

        # Generic: look for first identifier child
        for child in node.children:
            if child.type == "identifier":
                return _node_text(child, src)

        return None

    # ── Import extraction dispatch ────────────────────────────────

    def _extract_import(self, node) -> Tuple[List[Dict], List[Dict]]:
        lang = self.lang
        owner = self._scope[-1][0] if self._scope else self._module_name
        if lang == "python":
            nodes_out, edges_out = _extract_python_import(node, self.source_bytes, self.rel_file, owner)
        elif lang in ("javascript", "typescript"):
            nodes_out, edges_out = _extract_js_import(node, self.source_bytes, self.rel_file, lang, owner)
        elif lang == "java":
            nodes_out, edges_out = _extract_java_import(node, self.source_bytes, self.rel_file, owner)
        elif lang == "go":
            nodes_out, edges_out = _extract_go_import(node, self.source_bytes, self.rel_file, owner)
        elif lang == "rust":
            nodes_out, edges_out = _extract_rust_use(node, self.source_bytes, self.rel_file, owner)
        elif lang == "cpp":
            nodes_out, edges_out = _extract_cpp_include(node, self.source_bytes, self.rel_file, owner)
        else:
            return [], []

        # Resolve import files for cross-file edges
        for edge in edges_out:
            if edge["relationship"] in ("imports",):
                resolved = resolve_import_to_file(edge["to_name"], self.rel_file, self.lang, self.project_root)
                if resolved:
                    edge["to_file"] = resolved
                    # Update corresponding dependency node's file
                    for dep_node in nodes_out:
                        if dep_node["name"] == edge["to_name"] and dep_node["type"] == "dependency":
                            dep_node["file"] = resolved
        return nodes_out, edges_out

    # ── Inheritance resolution ────────────────────────────────────

    def _resolve_inheritance(self, node, ntype: str) -> Tuple[List[str], List[str]]:
        """Returns (bases, interfaces)."""
        bases, ifaces = [], []
        src = self.source_bytes
        config = self.config
        lang = self.lang

        if lang == "python" and ntype == "class_definition":
            arg_list = _child_by_field(node, "superclasses") or _child_type(node, "argument_list")
            if arg_list:
                for child in arg_list.children:
                    if child.type in ("identifier", "dotted_name"):
                        bases.append(_node_text(child, src))

        elif lang in ("javascript", "typescript"):
            for child in node.children:
                if child.type == "class_heritage":
                    # JS: class_heritage -> [extends, identifier, ...]
                    # TS: class_heritage -> [extends_clause -> [extends, identifier], ...]
                    for sub in child.children:
                        if sub.type == "extends_clause":
                            # TypeScript style - unwrap extends_clause
                            for grandchild in sub.children:
                                if grandchild.type == "extends":
                                    continue
                                elif grandchild.type in ("identifier", "type_identifier", "member_expression"):
                                    bases.append(_node_text(grandchild, src))
                        elif sub.type == "implements_clause":
                            # TypeScript interfaces
                            for grandchild in sub.children:
                                if grandchild.type in ("type_identifier", "identifier"):
                                    ifaces.append(_node_text(grandchild, src))
                        elif sub.type == "extends":
                            # JavaScript style - next node is the parent class
                            pass
                        elif sub.type in ("identifier", "type_identifier"):
                            # Parent class name (after extends keyword)
                            bases.append(_node_text(sub, src))

        elif lang == "java":
            for child in node.children:
                if child.type == "superclass":
                    for sc in child.children:
                        if sc.type == "type_identifier":
                            bases.append(_node_text(sc, src))
                elif child.type in ("super_interfaces", "extends_interfaces"):
                    for sc in child.children:
                        if sc.type in ("type_list", "interface_type_list"):
                            for t in sc.children:
                                if t.type == "type_identifier":
                                    ifaces.append(_node_text(t, src))

        elif lang == "cpp":
            for child in node.children:
                if child.type == "base_class_clause":
                    for bc in child.children:
                        if bc.type in ("type_identifier", "qualified_identifier"):
                            bases.append(_node_text(bc, src))

        elif lang == "rust" and ntype == "impl_item":
            # impl Trait for Type
            trait_node = _child_by_field(node, "trait")
            if trait_node:
                ifaces.append(_node_text(trait_node, src))

        return bases, ifaces


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2: call-graph extraction (S-expression queries)
# Called from TreeSitterParser after tree is built, when ts_language is available
# ─────────────────────────────────────────────────────────────────────────────

def extract_call_edges(
    ts_language,
    tree_root,
    source_bytes: bytes,
    config: LanguageConfig,
    nodes_by_name: Dict[str, Dict],
    rel_file: str,
) -> List[Dict]:
    """
    Second pass: find call edges using S-expression queries.
    Marked as INFERRED confidence (matching Graphify convention).
    """
    try:
        from tree_sitter import Language, Query
    except ImportError:
        return []

    call_edges = []
    seen: Set[Tuple[str, str]] = set()

    for query_str in config.call_queries:
        try:
            query = Query(ts_language, query_str)
            captures = query.captures(tree_root)
            for node, capture_name in captures:
                callee_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").strip()
                if not callee_text or len(callee_text) > 80:
                    continue
                # Find the enclosing function/method
                caller = _find_enclosing_function(node, nodes_by_name)
                if not caller:
                    continue
                key = (caller, callee_text)
                if key in seen:
                    continue
                seen.add(key)
                caller_file = nodes_by_name.get(caller, {}).get("file", rel_file)
                call_edges.append(_make_edge(
                    caller, caller_file,
                    callee_text, rel_file,
                    "calls",
                    config.default_edge_weight("calls"),
                    confidence=0.7,
                    provenance="tree_sitter_inferred",
                ))
        except Exception:
            continue

    return call_edges


def _find_enclosing_function(node, nodes_by_name: Dict[str, Dict]) -> Optional[str]:
    """Walk up parent chain to find nearest function/method node name."""
    FUNC_TYPES = {
        "function_definition", "async_function_definition",
        "function_declaration", "method_declaration", "method_definition",
        "function_item", "arrow_function",
    }
    cur = node.parent
    while cur:
        if cur.type in FUNC_TYPES:
            # Try to find its name in our nodes dict
            for name, nd in nodes_by_name.items():
                if nd.get("line_start", 0) <= cur.start_point[0] + 1 <= nd.get("line_end", 0):
                    if nd["type"] in ("function", "method"):
                        return name
        cur = cur.parent
    return None
