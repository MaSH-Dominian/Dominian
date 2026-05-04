"""
AgentGraph Intelligence - Python Parser
Uses Python's built-in AST module for perfect, zero-dependency parsing.
Extracts every symbol, relationship, complexity metric, and quality signal.
"""

import ast
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

from .import_resolver import resolve_import_to_file


class PythonParser:
    """
    Production-grade Python parser using the built-in AST module.
    Handles simple scripts to 100k+ line enterprise systems identically.
    """

    LANGUAGE = "python"
    EXTENSIONS = {".py", ".pyw", ".pyi"}

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        """
        Parse a Python file and return all nodes and edges.
        Returns: {"nodes": [...], "edges": [...], "errors": [...]}
        """
        path = Path(file_path)
        nodes, edges, errors = [], [], []

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree   = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        lines    = source.splitlines()
        rel_file = str(path)

        # Module-level node — use full filename to avoid collisions with symbols named after the module stem
        module_node = {
            "name":       path.name,  # e.g. "main.py" instead of "main" to avoid collisions
            "type":       "module",
            "file":       rel_file,
            "language":   self.LANGUAGE,
            "line_start": 1,
            "line_end":   len(lines),
            "complexity": 0,
            "quality":    100.0,
            "signature":  f"module {path.name}",
            "docstring":  ast.get_docstring(tree) or "",
            "metadata":   {
                "imports": [],
                "from_imports": [],
                "total_lines": len(lines),
                "blank_lines": sum(1 for l in lines if not l.strip()),
            }
        }

        visitor = _PythonVisitor(rel_file, lines, module_node)
        visitor.visit(tree)

        nodes  = visitor.nodes
        edges  = visitor.edges
        errors = visitor.errors

        # Quality scoring pass
        for node in nodes:
            node["quality"] = self._score_quality(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _score_quality(self, node: Dict) -> float:
        score = 100.0
        cx = node.get("complexity", 0)
        lines = node.get("line_end", 0) - node.get("line_start", 0)

        # Penalize complexity
        if cx > 10: score -= 30
        elif cx > 7: score -= 20
        elif cx > 5: score -= 10
        elif cx > 3: score -= 5

        # Penalize huge functions/classes
        if node["type"] == "function":
            if lines > 100: score -= 20
            elif lines > 50: score -= 10
        elif node["type"] == "class":
            if lines > 300: score -= 20
            elif lines > 150: score -= 10

        # Reward docstrings
        if not node.get("docstring"):
            if node["type"] in ("function", "method", "class"):
                score -= 10

        return max(0.0, min(100.0, score))


class _PythonVisitor(ast.NodeVisitor):
    """
    AST visitor that extracts every meaningful symbol and relationship.
    """

    def __init__(self, file: str, lines: List[str], module_node: Dict):
        self.file     = file
        self.lines    = lines
        self.nodes    = [module_node]
        self.edges    = []
        self.errors   = []
        self._scope   = [module_node["name"]]   # scope stack
        self._cls_stack: List[str] = []          # class stack
        self._imports: Dict[str, str] = {}       # alias -> real name

        # Collect imports for the module node — use the same list refs so mutations propagate
        self._module_imports: List[str]      = module_node["metadata"]["imports"]
        self._module_from_imports: List[str] = module_node["metadata"]["from_imports"]

    # ─────────────────────────────────────────────
    # IMPORTS
    # ─────────────────────────────────────────────

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name   = alias.asname or alias.name
            module = alias.name
            self._imports[name] = module
            self._module_imports.append(module)

            # Resolve the actual file path for this import
            target_file = self._resolve_module_file(module)
            # If resolved to a different file, use that as the dependency node's file
            dep_file = target_file if target_file != self.file else self.file

            dep_node = {
                "name":       module,
                "type":       "dependency",
                "file":       dep_file,
                "language":   "python",
                "line_start": node.lineno,
                "line_end":   node.lineno,
                "complexity": 0,
                "quality":    100.0,
                "signature":  f"import {module}",
                "docstring":  "",
                "metadata":   {"alias": alias.asname or "", "module_path": module, "resolved_file": target_file},
            }
            self.nodes.append(dep_node)
            # Create cross-file edge - target file is the resolved module file
            self.edges.append({
                "from_name": self._scope[0],
                "from_file": self.file,
                "to_name":   module,
                "to_file":   target_file,
                "relationship": "imports",
                "weight": 5.0,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            name     = alias.asname or alias.name
            fullname = f"{module}.{alias.name}" if module else alias.name
            self._imports[name] = fullname
            self._module_from_imports.append(fullname)

            # Resolve the actual file path for this import
            target_file = self._resolve_module_file(module) if module else self.file
            dep_file = target_file if target_file != self.file else self.file

            dep_node = {
                "name":       fullname,
                "type":       "dependency",
                "file":       dep_file,
                "language":   "python",
                "line_start": node.lineno,
                "line_end":   node.lineno,
                "complexity": 0,
                "quality":    100.0,
                "signature":  f"from {module} import {alias.name}",
                "docstring":  "",
                "metadata":   {"module": module, "symbol": alias.name, "module_path": module, "resolved_file": target_file},
            }
            self.nodes.append(dep_node)
            # Create cross-file edge - target file is the resolved module file
            self.edges.append({
                "from_name": self._scope[0],
                "from_file": self.file,
                "to_name":   fullname,
                "to_file":   target_file,
                "relationship": "imports",
                "weight": 6.0,
            })
        self.generic_visit(node)

    # ─────────────────────────────────────────────
    # CLASSES
    # ─────────────────────────────────────────────

    def visit_ClassDef(self, node: ast.ClassDef):
        complexity = self._class_complexity(node)
        docstring  = ast.get_docstring(node) or ""
        bases      = [self._name(b) for b in node.bases]
        decorators = [self._name(d) for d in node.decorator_list]

        class_node = {
            "name":       node.name,
            "type":       "class",
            "file":       self.file,
            "language":   "python",
            "line_start": node.lineno,
            "line_end":   node.end_lineno or node.lineno,
            "complexity": complexity,
            "quality":    100.0,
            "signature":  self._class_signature(node, bases),
            "docstring":  docstring,
            "metadata":   {
                "bases":      bases,
                "decorators": decorators,
                "methods":    [],
                "attributes": [],
            }
        }
        self.nodes.append(class_node)

        # Inheritance edges
        for base in bases:
            if base and base != "object":
                real = self._imports.get(base, base)
                self.edges.append({
                    "from_name": node.name,
                    "from_file": self.file,
                    "to_name":   real,
                    "to_file":   self.file,
                    "relationship": "inherits",
                    "weight": 9.0,
                })

        # Edge from enclosing scope
        if self._scope:
            self.edges.append({
                "from_name": self._scope[-1],
                "from_file": self.file,
                "to_name":   node.name,
                "to_file":   self.file,
                "relationship": "defines",
                "weight": 8.0,
            })

        self._scope.append(node.name)
        self._cls_stack.append(node.name)
        self.generic_visit(node)
        self._cls_stack.pop()
        self._scope.pop()

    def _class_signature(self, node: ast.ClassDef, bases: List[str]) -> str:
        decs = "".join(f"@{d}\n" for d in [self._name(d) for d in node.decorator_list])
        base_str = f"({', '.join(bases)})" if bases else ""
        return f"{decs}class {node.name}{base_str}:"

    def _class_complexity(self, node: ast.ClassDef) -> int:
        """Sum of method complexities, normalized."""
        total = 0
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total += self._cyclomatic_complexity(child)
        return min(total, 20)

    # ─────────────────────────────────────────────
    # FUNCTIONS / METHODS
    # ─────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node, is_async=True)

    def _visit_function(self, node, is_async: bool = False):
        complexity = self._cyclomatic_complexity(node)
        docstring  = ast.get_docstring(node) or ""
        decorators = [self._name(d) for d in node.decorator_list]
        is_method  = bool(self._cls_stack)
        returns    = self._annotation(node.returns) if node.returns else ""
        params     = self._extract_params(node)

        fname = node.name
        # Use qualified name for methods: ClassName.method_name
        qual_name = f"{self._cls_stack[-1]}.{fname}" if is_method else fname

        func_node = {
            "name":       qual_name,
            "type":       "method" if is_method else "function",
            "file":       self.file,
            "language":   "python",
            "line_start": node.lineno,
            "line_end":   node.end_lineno or node.lineno,
            "complexity": complexity,
            "quality":    100.0,
            "signature":  self._function_signature(node, params, returns, is_async),
            "docstring":  docstring,
            "metadata":   {
                "params":      params,
                "returns":     returns,
                "decorators":  decorators,
                "is_async":    is_async,
                "is_property": "property" in decorators,
                "is_static":   "staticmethod" in decorators,
                "is_class":    "classmethod" in decorators,
                "calls":       [],
            }
        }
        self.nodes.append(func_node)

        # Edge from enclosing scope
        if self._scope:
            self.edges.append({
                "from_name": self._scope[-1],
                "from_file": self.file,
                "to_name":   qual_name,
                "to_file":   self.file,
                "relationship": "defines",
                "weight": 7.0,
            })

        # Extract call edges
        calls = self._extract_calls(node)
        func_node["metadata"]["calls"] = calls
        for call in calls:
            real = self._imports.get(call, call)
            self.edges.append({
                "from_name": qual_name,
                "from_file": self.file,
                "to_name":   real,
                "to_file":   self.file,
                "relationship": "calls",
                "weight": 6.0,
            })

        self._scope.append(qual_name)
        self.generic_visit(node)
        self._scope.pop()

    def _function_signature(
        self, node, params: List[Dict], returns: str, is_async: bool
    ) -> str:
        prefix = "async def" if is_async else "def"
        param_str = ", ".join(
            f"{p['name']}: {p['annotation']}" if p.get("annotation") else p["name"]
            for p in params
        )
        ret = f" -> {returns}" if returns else ""
        return f"{prefix} {node.name}({param_str}){ret}:"

    def _extract_params(self, node) -> List[Dict]:
        params = []
        args   = node.args
        for arg in args.args + args.posonlyargs + args.kwonlyargs:
            params.append({
                "name":        arg.arg,
                "annotation":  self._annotation(arg.annotation) if arg.annotation else "",
                "kind":        "positional",
            })
        if args.vararg:
            params.append({"name": f"*{args.vararg.arg}", "annotation": "", "kind": "vararg"})
        if args.kwarg:
            params.append({"name": f"**{args.kwarg.arg}", "annotation": "", "kind": "kwarg"})
        return params

    def _extract_calls(self, node) -> List[str]:
        _BUILTINS = {
            "print", "len", "all", "any", "range", "enumerate", "zip", "map", "filter",
            "open", "isinstance", "hasattr", "getattr", "setattr", "type", "str", "int",
            "float", "bool", "list", "dict", "tuple", "set", "frozenset", "sum", "min",
            "max", "sorted", "reversed", "abs", "round", "divmod", "pow", "chr", "ord",
            "hex", "oct", "bin", "bytes", "bytearray", "memoryview", "hash", "id",
            "repr", "format", "vars", "locals", "globals", "dir", "eval", "exec",
            "compile", "ascii", "breakpoint", "help", "input", "exit", "quit",
            "copyright", "credits", "license", "ValueError", "TypeError", "KeyError",
            "IndexError", "AttributeError", "RuntimeError", "Exception", "OSError",
            "IOError", "NotImplementedError", "StopIteration", "GeneratorExit",
            "AssertionError", "ImportError", "ModuleNotFoundError", "ZeroDivisionError",
        }
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = self._call_name(child.func)
                if not name:
                    continue
                # Skip self/cls/super method calls (internal calls)
                if name.startswith("self.") or name.startswith("cls.") or name.startswith("super"):
                    continue
                # Skip built-in calls
                base_name = name.split(".")[0]
                if base_name in _BUILTINS:
                    continue
                # Skip list/dict/set methods
                if base_name in ("append", "extend", "insert", "remove", "pop", "clear",
                                   "copy", "index", "count", "sort", "reverse", "add",
                                   "discard", "update", "union", "intersection", "difference"):
                    continue
                if name not in calls:
                    calls.append(name)
        return calls[:50]  # cap to avoid noise

    def _call_name(self, node) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
                return ".".join(reversed(parts))
        return None

    def _resolve_module_file(self, module: str) -> str:
        """Resolve the actual file path for a module import."""
        from pathlib import Path
        
        # Convert module name to potential file path
        if module.startswith('.'):
            # Relative import - resolve relative to current file
            current_dir = Path(self.file).parent
            parts = module.lstrip('.').split('.')
            if parts[0]:  # Has parts after removing dots
                for part in parts:
                    current_dir = current_dir / part
            target_file = current_dir / "__init__.py"
            if not target_file.exists():
                target_file = current_dir.with_suffix('.py')
        else:
            # Absolute import - try common patterns
            current_dir = Path(self.file).parent
            
            # Convert dots to path separators
            module_path = module.replace('.', '/')
            
            # Try as direct file in same directory
            target_file = current_dir / f"{module_path}.py"
            if target_file.exists():
                return str(target_file)
            
            # Try as subdirectory with __init__.py
            target_file = current_dir / module_path / "__init__.py"
            if target_file.exists():
                return str(target_file)
            
            # Try as package in parent directories
            parent_dir = current_dir
            for _ in range(3):  # Check up to 3 levels up
                parent_target = parent_dir / module_path / "__init__.py"
                if parent_target.exists():
                    return str(parent_target)
                parent_target2 = parent_dir / f"{module_path}.py"
                if parent_target2.exists():
                    return str(parent_target2)
                parent_dir = parent_dir.parent
            
            # Fallback - keep original behavior but mark as unresolved
            target_file = self.file
        
        return str(target_file) if Path(target_file).exists() else self.file

    # ─────────────────────────────────────────────
    # VARIABLES / ASSIGNMENTS
    # ─────────────────────────────────────────────

    def visit_Assign(self, node: ast.Assign):
        # Only capture module-level and class-level assignments (not inside functions)
        depth = len(self._scope)
        if depth > 2:
            self.generic_visit(node)
            return
        for target in node.targets:
            name = self._assignment_target_name(target)
            if name and not name.startswith("_"):
                val_type = type(node.value).__name__
                var_node = {
                    "name":       name,
                    "type":       "variable",
                    "file":       self.file,
                    "language":   "python",
                    "line_start": node.lineno,
                    "line_end":   node.end_lineno or node.lineno,
                    "complexity": 0,
                    "quality":    100.0,
                    "signature":  self._source_line(node.lineno),
                    "docstring":  "",
                    "metadata":   {"value_type": val_type},
                }
                self.nodes.append(var_node)
                if self._scope:
                    self.edges.append({
                        "from_name": self._scope[-1],
                        "from_file": self.file,
                        "to_name":   name,
                        "to_file":   self.file,
                        "relationship": "defines",
                        "weight": 3.0,
                    })
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        depth = len(self._scope)
        if depth > 2:
            self.generic_visit(node)
            return
        name = self._assignment_target_name(node.target)
        if name and not name.startswith("_"):
            ann = self._annotation(node.annotation)
            var_node = {
                "name":       name,
                "type":       "variable",
                "file":       self.file,
                "language":   "python",
                "line_start": node.lineno,
                "line_end":   node.end_lineno or node.lineno,
                "complexity": 0,
                "quality":    100.0,
                "signature":  f"{name}: {ann}",
                "docstring":  "",
                "metadata":   {"annotation": ann},
            }
            self.nodes.append(var_node)
        self.generic_visit(node)

    # ─────────────────────────────────────────────
    # COMPLEXITY
    # ─────────────────────────────────────────────

    def _cyclomatic_complexity(self, node) -> int:
        """McCabe cyclomatic complexity."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (
                ast.If, ast.While, ast.For, ast.AsyncFor,
                ast.ExceptHandler, ast.With, ast.AsyncWith,
                ast.Assert, ast.comprehension,
            )):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return min(complexity, 20)

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _name(self, node) -> str:
        if isinstance(node, ast.Name):      return node.id
        if isinstance(node, ast.Attribute): return f"{self._name(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):      return self._name(node.func)
        if isinstance(node, ast.Constant):  return str(node.value)
        return ""

    def _annotation(self, node) -> str:
        if node is None: return ""
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _assignment_target_name(self, target) -> Optional[str]:
        if isinstance(target, ast.Name):      return target.id
        if isinstance(target, ast.Attribute): return target.attr
        if isinstance(target, ast.Subscript): return None
        return None

    def _source_line(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""
