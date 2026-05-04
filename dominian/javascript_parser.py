"""
AgentGraph Intelligence - JavaScript / TypeScript Parser
Regex-based fallback for JS/TS when tree-sitter is unavailable.
Fast, lightweight, production-grade regex extraction.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from .import_resolver import resolve_import_to_file


class JavaScriptParser:
    """
    Regex-based parser for JavaScript, TypeScript, JSX, TSX.
    Handles modern syntax: arrow functions, classes, destructuring, decorators, generics.
    """

    LANGUAGE   = "javascript"
    EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    # JavaScript keywords that should NOT be treated as function/method names
    _JS_KEYWORDS = {
        "if", "else", "for", "while", "do", "switch", "case", "default",
        "break", "continue", "return", "try", "catch", "finally", "throw",
        "with", "debugger", "function", "var", "let", "const", "class",
        "extends", "import", "export", "from", "as", "new", "this", "super",
        "typeof", "instanceof", "void", "delete", "in", "of", "yield", "await",
        "async", "static", "public", "private", "protected", "readonly",
        "interface", "type", "enum", "namespace", "module", "declare",
        "abstract", "implements", "package", "synchronized", "native",
        "transient", "volatile", "get", "set", "constructor",
    }

    # Regex patterns for symbol extraction
    _RE_FUNCTION = re.compile(
        r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*([\w\[\]<>|&\s]+))?',
        re.MULTILINE
    )
    _RE_ARROW = re.compile(
        r'(?:const|let|var)\s+(\w+)\s*(?::\s*[\w\[\]<>|&\s]+)?\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*(\w[\w\[\]<>|&\s]*))?\s*=>',
        re.MULTILINE
    )
    _RE_CLASS = re.compile(
        r'(?:export\s+(?:default\s+)?)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?',
        re.MULTILINE
    )
    _RE_METHOD = re.compile(
        r'(?:(?:public|private|protected|static|async|readonly|override)\s+)*(\w+)\s*\(([^)]*)\)\s*(?::\s*\w[\w\[\]<>|&\s]*)?\s*\{',
        re.MULTILINE
    )
    _RE_INTERFACE = re.compile(
        r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([\w\s,]+))?',
        re.MULTILINE
    )
    _RE_TYPE = re.compile(
        r'(?:export\s+)?type\s+(\w+)\s*=',
        re.MULTILINE
    )
    _RE_IMPORT = re.compile(
        r'import\s+(?:(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)\s+from\s+)?["\']([^"\']+)["\'];?',
        re.MULTILINE
    )
    _RE_EXPORT = re.compile(
        r'export\s+(?:default\s+)?(?:class|function|const|let|var|interface|type)?\s*(\w+)',
        re.MULTILINE
    )

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        """Parse a JS/TS file and return all nodes and edges."""
        path = Path(file_path)
        nodes, edges, errors = [], [], []

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        rel_file = str(path)
        module_name = path.stem

        # Module node
        module_node = {
            "name":       path.name,   # e.g. "app.js" instead of "app" to avoid collisions
            "type":       "module",
            "file":       rel_file,
            "language":   self.LANGUAGE,
            "line_start": 1,
            "line_end":   len(lines),
            "complexity": 0,
            "quality":    100.0,
            "signature":  f"module {path.name}",
            "docstring":  "",
            "metadata":   {"total_lines": len(lines)},
        }
        nodes.append(module_node)

        # Track defined names to avoid treating them as calls
        defined_names: set = set()

        # ── Extract classes ──
        for m in self._RE_CLASS.finditer(source):
            class_name = m.group(1)
            if not class_name or class_name in self._JS_KEYWORDS:
                continue
            defined_names.add(class_name)
            lineno = source[:m.start()].count("\n") + 1
            bases = []
            if m.group(2):
                bases = [b.strip() for b in m.group(2).split(",") if b.strip()]
            interfaces = []
            if m.group(3):
                interfaces = [i.strip() for i in m.group(3).split(",") if i.strip()]

            class_node = {
                "name":       class_name,
                "type":       "class",
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno + 20,  # Approximate
                "complexity": 0,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {
                    "bases": bases,
                    "implements": interfaces,
                    "methods": [],
                },
            }
            nodes.append(class_node)

            # defines edge
            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   class_name,
                "to_file":   rel_file,
                "relationship": "defines",
                "weight": 8.0,
            })

            # inheritance edges
            for base in bases:
                if base and base not in self._JS_KEYWORDS:
                    edges.append({
                        "from_name": class_name,
                        "from_file": rel_file,
                        "to_name":   base,
                        "to_file":   rel_file,
                        "relationship": "inherits",
                        "weight": 9.0,
                    })

            # interface edges
            for iface in interfaces:
                if iface and iface not in self._JS_KEYWORDS:
                    edges.append({
                        "from_name": class_name,
                        "from_file": rel_file,
                        "to_name":   iface,
                        "to_file":   rel_file,
                        "relationship": "implements",
                        "weight": 7.0,
                    })

            # Extract methods inside this class
            class_start = m.start()
            class_end   = self._find_block_end(source, class_start)
            class_body  = source[class_start:class_end]
            for mm in self._RE_METHOD.finditer(class_body):
                method_name = mm.group(1)
                if not method_name or method_name in self._JS_KEYWORDS:
                    continue
                defined_names.add(method_name)
                method_lineno = lineno + class_body[:mm.start()].count("\n")
                qual_name = f"{class_name}.{method_name}"

                method_node = {
                    "name":       qual_name,
                    "type":       "method",
                    "file":       rel_file,
                    "language":   self.LANGUAGE,
                    "line_start": method_lineno,
                    "line_end":   method_lineno + 10,
                    "complexity": 1,
                    "quality":    100.0,
                    "signature":  mm.group(0).strip(),
                    "docstring":  "",
                    "metadata":   {"params": mm.group(2) or ""},
                }
                nodes.append(method_node)
                class_node["metadata"]["methods"].append(qual_name)

                # defines edge from class to method
                edges.append({
                    "from_name": class_name,
                    "from_file": rel_file,
                    "to_name":   qual_name,
                    "to_file":   rel_file,
                    "relationship": "defines",
                    "weight": 7.0,
                })

        # ── Extract top-level functions ──
        for m in self._RE_FUNCTION.finditer(source):
            func_name = m.group(1)
            if not func_name or func_name in self._JS_KEYWORDS:
                continue
            defined_names.add(func_name)
            lineno = source[:m.start()].count("\n") + 1

            func_node = {
                "name":       func_name,
                "type":       "function",
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno + 20,
                "complexity": 1,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {"params": m.group(2) or "", "returns": m.group(3) or ""},
            }
            nodes.append(func_node)

            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   func_name,
                "to_file":   rel_file,
                "relationship": "defines",
                "weight": 7.0,
            })

        # ── Extract arrow functions (const/let declarations) ──
        for m in self._RE_ARROW.finditer(source):
            arrow_name = m.group(1)
            if not arrow_name or arrow_name in self._JS_KEYWORDS:
                continue
            defined_names.add(arrow_name)
            lineno = source[:m.start()].count("\n") + 1

            arrow_node = {
                "name":       arrow_name,
                "type":       "function",
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno + 20,
                "complexity": 1,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {
                    "params": m.group(2) or "",
                    "returns": m.group(3) or "",
                    "is_arrow": True,
                },
            }
            nodes.append(arrow_node)

            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   arrow_name,
                "to_file":   rel_file,
                "relationship": "defines",
                "weight": 6.0,
            })

        # ── Extract interfaces ──
        for m in self._RE_INTERFACE.finditer(source):
            iface_name = m.group(1)
            if not iface_name or iface_name in self._JS_KEYWORDS:
                continue
            defined_names.add(iface_name)
            lineno = source[:m.start()].count("\n") + 1
            extends = []
            if m.group(2):
                extends = [e.strip() for e in m.group(2).split(",") if e.strip()]

            iface_node = {
                "name":       iface_name,
                "type":       "interface",
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno + 15,
                "complexity": 0,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {"extends": extends},
            }
            nodes.append(iface_node)

            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   iface_name,
                "to_file":   rel_file,
                "relationship": "defines",
                "weight": 7.0,
            })

            for ext in extends:
                if ext and ext not in self._JS_KEYWORDS:
                    edges.append({
                        "from_name": iface_name,
                        "from_file": rel_file,
                        "to_name":   ext,
                        "to_file":   rel_file,
                        "relationship": "extends",
                        "weight": 6.0,
                    })

        # ── Extract type aliases ──
        for m in self._RE_TYPE.finditer(source):
            type_name = m.group(1)
            if not type_name or type_name in self._JS_KEYWORDS:
                continue
            defined_names.add(type_name)
            lineno = source[:m.start()].count("\n") + 1

            type_node = {
                "name":       type_name,
                "type":       "variable",  # TypeScript type aliases treated as variables
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno + 5,
                "complexity": 0,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {"is_type_alias": True},
            }
            nodes.append(type_node)

            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   type_name,
                "to_file":   rel_file,
                "relationship": "defines",
                "weight": 4.0,
            })

        # ── Extract imports ──
        for m in self._RE_IMPORT.finditer(source):
            module_path = m.group(1)
            if not module_path:
                continue
            lineno = source[:m.start()].count("\n") + 1

            dep_node = {
                "name":       module_path,
                "type":       "dependency",
                "file":       rel_file,
                "language":   self.LANGUAGE,
                "line_start": lineno,
                "line_end":   lineno,
                "complexity": 0,
                "quality":    100.0,
                "signature":  m.group(0).strip(),
                "docstring":  "",
                "metadata":   {"import_path": module_path},
            }
            nodes.append(dep_node)

            # Resolve to actual file
            resolved = resolve_import_to_file(module_path, rel_file, self.LANGUAGE, root_path)
            target_file = resolved if resolved else rel_file

            edges.append({
                "from_name": module_name,
                "from_file": rel_file,
                "to_name":   module_path,
                "to_file":   target_file,
                "relationship": "imports",
                "weight": 5.0,
            })

        # ── Extract exports ──
        for m in self._RE_EXPORT.finditer(source):
            exported_name = m.group(1)
            if not exported_name or exported_name in self._JS_KEYWORDS:
                continue
            lineno = source[:m.start()].count("\n") + 1

            edges.append({
                "from_name": exported_name,
                "from_file": rel_file,
                "to_name":   module_name,
                "to_file":   rel_file,
                "relationship": "exports",
                "weight": 5.0,
            })

        # ── Extract call edges (best effort via regex) ──
        # Find all call expressions: name(...) or obj.name(...)
        call_pattern = re.compile(r'([\w.]+)\s*\(')
        for line_no, line in enumerate(lines, 1):
            for cm in call_pattern.finditer(line):
                callee = cm.group(1)
                # Skip if it's a defined name or keyword
                if callee in self._JS_KEYWORDS or callee in defined_names:
                    continue
                # Skip common non-function patterns
                if callee in ("if", "for", "while", "switch", "catch"):
                    continue
                # Skip object properties that aren't calls (e.g., console.log is OK)
                parts = callee.split(".")
                if parts[-1] in self._JS_KEYWORDS:
                    continue

                edges.append({
                    "from_name": module_name,
                    "from_file": rel_file,
                    "to_name":   callee,
                    "to_file":   rel_file,
                    "relationship": "calls",
                    "weight": 4.0,
                })

        # Quality scoring pass
        for node in nodes:
            node["quality"] = self._score_quality(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _find_block_end(self, source: str, start: int) -> int:
        """Find the matching } for a block starting at start."""
        brace_depth = 0
        in_string = False
        string_char = None
        i = start
        while i < len(source):
            ch = source[i]
            if not in_string:
                if ch in ('"', "'", "`"):
                    in_string = True
                    string_char = ch
                elif ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        return i + 1
            else:
                if ch == string_char and source[i - 1] != "\\":
                    in_string = False
            i += 1
        return len(source)

    def _score_quality(self, node: Dict) -> float:
        score = 100.0
        lines = node.get("line_end", 0) - node.get("line_start", 0)
        if node["type"] == "function":
            if lines > 100: score -= 20
            elif lines > 50: score -= 10
        elif node["type"] == "class":
            if lines > 300: score -= 20
            elif lines > 150: score -= 10
        if not node.get("docstring"):
            if node["type"] in ("function", "method", "class"):
                score -= 10
        return max(0.0, min(100.0, score))
