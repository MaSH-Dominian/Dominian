"""
AgentGraph Intelligence - Java / Go / Rust / C++ Parsers
Regex + structural analysis for compiled languages.
Each parser extracts classes, functions, interfaces, imports, and relationships.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from import_resolver import resolve_import_to_file


# ─────────────────────────────────────────────────────────────────────────────
# JAVA
# ─────────────────────────────────────────────────────────────────────────────

class JavaParser:
    LANGUAGE  = "java"
    EXTENSIONS = {".java"}

    _RE_PKG     = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.M)
    _RE_IMPORT  = re.compile(r'^\s*import\s+(?:static\s+)?([\w.*]+)\s*;', re.M)
    _RE_CLASS   = re.compile(
        r'(?:public|private|protected|abstract|final|static)?\s*'
        r'(?:class|enum|record)\s+(\w+)'
        r'(?:\s+extends\s+(\w+))?'
        r'(?:\s+implements\s+([\w,\s]+))?',
        re.M
    )
    _RE_IFACE   = re.compile(
        r'(?:public|private|protected)?\s*interface\s+(\w+)'
        r'(?:\s+extends\s+([\w,\s]+))?',
        re.M
    )
    _RE_METHOD  = re.compile(
        r'(?:public|private|protected|static|final|synchronized|native|abstract|\s)+'
        r'(?:<[\w,\s?]+>\s+)?'
        r'([\w<>\[\]]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*[\{;]',
        re.M
    )
    _RE_ANNOT   = re.compile(r'@(\w+)(?:\([^)]*\))?', re.M)

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        path = Path(file_path)
        nodes, edges, errors = [], [], []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        lines    = source.splitlines()
        rel_file = str(path)

        pkg = (self._RE_PKG.search(source) or ["", ""])[1] if self._RE_PKG.search(source) else ""

        module_node = {
            "name": path.stem, "type": "module",
            "file": rel_file, "language": self.LANGUAGE,
            "line_start": 1, "line_end": len(lines),
            "complexity": 0, "quality": 100.0,
            "signature": f"package {pkg}" if pkg else path.stem,
            "docstring": "", "metadata": {"package": pkg},
        }
        nodes.append(module_node)

        # Imports
        for m in self._RE_IMPORT.finditer(source):
            dep = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append(self._dep(dep, rel_file, lineno, f"import {dep}"))
            edges.append(self._edge(path.stem, rel_file, dep, rel_file, "imports", 5.0))

        # Interfaces
        for m in self._RE_IFACE.finditer(source):
            iname, extends = m.groups()
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": iname, "type": "interface",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 30,
                "complexity": 0, "quality": 100.0,
                "signature": f"interface {iname}" + (f" extends {extends}" if extends else ""),
                "docstring": self._javadoc(source, m.start()),
                "metadata": {"extends": extends.split(",") if extends else []},
            })
            edges.append(self._edge(path.stem, rel_file, iname, rel_file, "defines", 8.0))

        # Classes
        class_names = set()
        for m in self._RE_CLASS.finditer(source):
            cname, extends, implements = m.groups()
            class_names.add(cname)
            lineno = source[:m.start()].count("\n") + 1
            cx = self._complexity_estimate(source, m.start())
            nodes.append({
                "name": cname, "type": "class",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 100,
                "complexity": cx, "quality": 100.0,
                "signature": m.group(0).strip(),
                "docstring": self._javadoc(source, m.start()),
                "metadata": {
                    "extends": extends or "",
                    "implements": [i.strip() for i in implements.split(",")] if implements else [],
                    "annotations": self._annots_before(source, m.start()),
                },
            })
            edges.append(self._edge(path.stem, rel_file, cname, rel_file, "defines", 8.0))
            if extends:
                edges.append(self._edge(cname, rel_file, extends, rel_file, "inherits", 9.0))
            if implements:
                for iface in implements.split(","):
                    iface = iface.strip()
                    if iface:
                        edges.append(self._edge(cname, rel_file, iface, rel_file, "implements", 8.0))

        # Methods
        for m in self._RE_METHOD.finditer(source):
            ret_type, mname, params = m.groups()
            if mname in class_names or ret_type in ("class", "interface", "enum"): continue
            lineno = source[:m.start()].count("\n") + 1
            cx = self._cyclo(source[m.start():m.start() + 1000])
            # Determine owning class
            owner = self._find_owner(source, m.start(), class_names) or path.stem
            qual  = f"{owner}.{mname}"
            nodes.append({
                "name": qual, "type": "method",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 30,
                "complexity": cx, "quality": 100.0,
                "signature": f"{ret_type} {mname}({params})",
                "docstring": self._javadoc(source, m.start()),
                "metadata": {"owner": owner, "returns": ret_type, "params": params},
            })
            edges.append(self._edge(owner, rel_file, qual, rel_file, "defines", 7.0))

        for node in nodes:
            node["quality"] = self._score(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _find_owner(self, source: str, pos: int, class_names) -> Optional[str]:
        before = source[:pos]
        for cname in class_names:
            if cname in before:
                return cname
        return None

    def _complexity_estimate(self, source: str, start: int) -> int:
        chunk = source[start:start + 3000]
        return self._cyclo(chunk)

    def _cyclo(self, code: str) -> int:
        return min(1 + len(re.findall(
            r'\b(if|else|for|while|switch|case|catch|&&|\|\||\?:)\b', code
        )), 20)

    def _javadoc(self, source: str, pos: int) -> str:
        before = source[max(0, pos - 400):pos]
        m = re.search(r'/\*\*(.*?)\*/', before, re.DOTALL)
        if m:
            return re.sub(r'\s*\*\s?', ' ', m.group(1)).strip()
        return ""

    def _annots_before(self, source: str, pos: int) -> List[str]:
        before = source[max(0, pos - 300):pos]
        return [m.group(1) for m in self._RE_ANNOT.finditer(before)]

    def _dep(self, name: str, file: str, lineno: int, sig: str) -> Dict:
        return {"name": name, "type": "dependency", "file": file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno, "complexity": 0, "quality": 100.0,
                "signature": sig, "docstring": "", "metadata": {}}

    def _edge(self, fn, ff, tn, tf, rel, w) -> Dict:
        return {"from_name": fn, "from_file": ff, "to_name": tn, "to_file": tf,
                "relationship": rel, "weight": w}

    def _score(self, node: Dict) -> float:
        s = 100.0
        cx = node.get("complexity", 0)
        if cx > 10: s -= 30
        elif cx > 7: s -= 20
        elif cx > 5: s -= 10
        if not node.get("docstring") and node["type"] in ("method", "class"): s -= 10
        return max(0.0, min(100.0, s))


# ─────────────────────────────────────────────────────────────────────────────
# GO
# ─────────────────────────────────────────────────────────────────────────────

class GoParser:
    LANGUAGE   = "go"
    EXTENSIONS = {".go"}

    _RE_PKG    = re.compile(r'^\s*package\s+(\w+)', re.M)
    _RE_IMPORT = re.compile(r'"([\w./\-]+)"', re.M)
    _RE_STRUCT = re.compile(r'type\s+(\w+)\s+struct\s*\{', re.M)
    _RE_IFACE  = re.compile(r'type\s+(\w+)\s+interface\s*\{', re.M)
    _RE_FUNC   = re.compile(r'func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)(?:\s*\(([^)]*)\))?\s*\{', re.M)
    _RE_TYPE   = re.compile(r'type\s+(\w+)\s+(\w+)', re.M)

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        path = Path(file_path)
        nodes, edges, errors = [], [], []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        lines    = source.splitlines()
        rel_file = str(path)
        pkg_m    = self._RE_PKG.search(source)
        pkg      = pkg_m.group(1) if pkg_m else path.stem

        nodes.append({
            "name": pkg, "type": "module",
            "file": rel_file, "language": self.LANGUAGE,
            "line_start": 1, "line_end": len(lines),
            "complexity": 0, "quality": 100.0,
            "signature": f"package {pkg}", "docstring": "",
            "metadata": {"package": pkg},
        })

        # Imports (inside import blocks)
        import_block = re.search(r'import\s*\((.*?)\)', source, re.DOTALL)
        if import_block:
            for m in self._RE_IMPORT.finditer(import_block.group(1)):
                dep = m.group(1)
                resolved = resolve_import_to_file(dep, rel_file, self.LANGUAGE, root_path)
                target_file = resolved if resolved else rel_file
                nodes.append({"name": dep, "type": "dependency", "file": target_file,
                               "language": self.LANGUAGE, "line_start": 1, "line_end": 1,
                               "complexity": 0, "quality": 100.0,
                               "signature": f'import "{dep}"', "docstring": "", "metadata": {}})
                edges.append(self._edge(pkg, rel_file, dep, target_file, "imports", 5.0))

        # Structs
        struct_names = set()
        for m in self._RE_STRUCT.finditer(source):
            sname  = m.group(1)
            struct_names.add(sname)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": sname, "type": "class",  # structs are classes
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 20,
                "complexity": 0, "quality": 95.0,
                "signature": f"type {sname} struct", "docstring": self._godoc(source, m.start()),
                "metadata": {"kind": "struct"},
            })
            edges.append(self._edge(pkg, rel_file, sname, rel_file, "defines", 8.0))

        # Interfaces
        for m in self._RE_IFACE.finditer(source):
            iname  = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": iname, "type": "interface",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 20,
                "complexity": 0, "quality": 100.0,
                "signature": f"type {iname} interface", "docstring": self._godoc(source, m.start()),
                "metadata": {},
            })
            edges.append(self._edge(pkg, rel_file, iname, rel_file, "defines", 8.0))

        # Functions & Methods
        for m in self._RE_FUNC.finditer(source):
            recv_name, recv_type, fname, params, returns = m.groups()
            lineno  = source[:m.start()].count("\n") + 1
            cx      = self._cyclo(source[m.start():m.start() + 1500])
            is_meth = recv_type is not None
            qual    = f"({recv_type}).{fname}" if is_meth else fname
            owner   = recv_type or pkg

            nodes.append({
                "name": qual, "type": "method" if is_meth else "function",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 30,
                "complexity": cx, "quality": 100.0,
                "signature": f"func {f'({recv_name} {recv_type}) ' if is_meth else ''}{fname}({params or ''})" + (f" ({returns})" if returns else ""),
                "docstring": self._godoc(source, m.start()),
                "metadata": {"receiver": recv_type or "", "params": params or "", "returns": returns or ""},
            })
            edges.append(self._edge(owner, rel_file, qual, rel_file, "defines", 7.0))

        for node in nodes:
            if node["type"] not in ("module", "dependency"):
                node["quality"] = self._score(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _godoc(self, source: str, pos: int) -> str:
        before = source[max(0, pos - 200):pos]
        lines  = before.strip().splitlines()
        doc_lines = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                doc_lines.insert(0, stripped[2:].strip())
            else:
                break
        return " ".join(doc_lines)

    def _cyclo(self, code: str) -> int:
        return min(1 + len(re.findall(
            r'\b(if|else|for|switch|case|select|&&|\|\|)\b', code
        )), 20)

    def _edge(self, fn, ff, tn, tf, rel, w) -> Dict:
        return {"from_name": fn, "from_file": ff, "to_name": tn, "to_file": tf,
                "relationship": rel, "weight": w}

    def _score(self, node: Dict) -> float:
        s = 100.0
        cx = node.get("complexity", 0)
        if cx > 10: s -= 30
        elif cx > 7: s -= 20
        elif cx > 5: s -= 10
        if not node.get("docstring") and node["type"] in ("function", "method"): s -= 8
        return max(0.0, min(100.0, s))


# ─────────────────────────────────────────────────────────────────────────────
# RUST
# ─────────────────────────────────────────────────────────────────────────────

class RustParser:
    LANGUAGE   = "rust"
    EXTENSIONS = {".rs"}

    _RE_MOD    = re.compile(r'(?:^|\n)mod\s+(\w+)', re.M)
    _RE_USE    = re.compile(r'use\s+([\w::{},\s*]+)\s*;', re.M)
    _RE_STRUCT = re.compile(r'(?:pub\s+)?struct\s+(\w+)(?:<[^>]*>)?', re.M)
    _RE_ENUM   = re.compile(r'(?:pub\s+)?enum\s+(\w+)(?:<[^>]*>)?', re.M)
    _RE_TRAIT  = re.compile(r'(?:pub\s+)?trait\s+(\w+)(?:<[^>]*>)?(?:\s*:\s*[\w+\s]+)?', re.M)
    _RE_IMPL   = re.compile(r'impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)', re.M)
    _RE_FN     = re.compile(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)(?:<[^>]*>)?\s*\(([^)]*)\)(?:\s*->\s*([\w<>&\[\]\s:]+))?', re.M)
    _RE_CONST  = re.compile(r'(?:pub\s+)?const\s+(\w+)\s*:\s*([\w<>&\[\]\s:]+)\s*=', re.M)
    _RE_TYPE   = re.compile(r'(?:pub\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=', re.M)

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        path = Path(file_path)
        nodes, edges, errors = [], [], []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        lines    = source.splitlines()
        rel_file = str(path)
        mod_name = path.stem

        nodes.append({
            "name": mod_name, "type": "module",
            "file": rel_file, "language": self.LANGUAGE,
            "line_start": 1, "line_end": len(lines),
            "complexity": 0, "quality": 100.0,
            "signature": f"mod {mod_name}",
            "docstring": self._rustdoc(source, 0),
            "metadata": {},
        })

        # use statements
        for m in self._RE_USE.finditer(source):
            dep = m.group(1).strip()
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({"name": dep, "type": "dependency", "file": rel_file,
                           "language": self.LANGUAGE, "line_start": lineno, "line_end": lineno,
                           "complexity": 0, "quality": 100.0,
                           "signature": f"use {dep}", "docstring": "", "metadata": {}})
            edges.append(self._edge(mod_name, rel_file, dep, rel_file, "imports", 5.0))

        # Structs
        for m in self._RE_STRUCT.finditer(source):
            sname  = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": sname, "type": "class",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 20,
                "complexity": 0, "quality": 95.0,
                "signature": f"struct {sname}", "docstring": self._rustdoc(source, m.start()),
                "metadata": {"kind": "struct"},
            })
            edges.append(self._edge(mod_name, rel_file, sname, rel_file, "defines", 8.0))

        # Traits (interfaces in Rust)
        for m in self._RE_TRAIT.finditer(source):
            tname  = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": tname, "type": "interface",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 20,
                "complexity": 0, "quality": 100.0,
                "signature": f"trait {tname}", "docstring": self._rustdoc(source, m.start()),
                "metadata": {},
            })
            edges.append(self._edge(mod_name, rel_file, tname, rel_file, "defines", 8.0))

        # Impl blocks (trait implementations)
        for m in self._RE_IMPL.finditer(source):
            trait, target = m.groups()
            if trait:
                edges.append(self._edge(target, rel_file, trait, rel_file, "implements", 9.0))

        # Functions
        for m in self._RE_FN.finditer(source):
            fname, params, returns = m.groups()
            lineno = source[:m.start()].count("\n") + 1
            cx = self._cyclo(source[m.start():m.start() + 1500])
            nodes.append({
                "name": fname, "type": "function",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 30,
                "complexity": cx, "quality": 100.0,
                "signature": f"fn {fname}({params or ''})" + (f" -> {returns}" if returns else ""),
                "docstring": self._rustdoc(source, m.start()),
                "metadata": {"params": params or "", "returns": returns or ""},
            })
            edges.append(self._edge(mod_name, rel_file, fname, rel_file, "defines", 7.0))

        for node in nodes:
            if node["type"] not in ("module", "dependency"):
                node["quality"] = self._score(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _rustdoc(self, source: str, pos: int) -> str:
        before = source[max(0, pos - 300):pos]
        lines  = before.strip().splitlines()
        doc_lines = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("///"):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped.startswith("//!"):
                doc_lines.insert(0, stripped[3:].strip())
            else:
                break
        return " ".join(doc_lines)

    def _cyclo(self, code: str) -> int:
        return min(1 + len(re.findall(
            r'\b(if|else|for|while|loop|match|&&|\|\||\?)\b', code
        )), 20)

    def _edge(self, fn, ff, tn, tf, rel, w) -> Dict:
        return {"from_name": fn, "from_file": ff, "to_name": tn, "to_file": tf,
                "relationship": rel, "weight": w}

    def _score(self, node: Dict) -> float:
        s = 100.0
        cx = node.get("complexity", 0)
        if cx > 10: s -= 30
        elif cx > 7: s -= 20
        elif cx > 5: s -= 10
        if not node.get("docstring") and node["type"] in ("function",): s -= 5
        return max(0.0, min(100.0, s))


# ─────────────────────────────────────────────────────────────────────────────
# C / C++
# ─────────────────────────────────────────────────────────────────────────────

class CppParser:
    LANGUAGE   = "cpp"
    EXTENSIONS = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx"}

    _RE_INCLUDE = re.compile(r'#include\s*[<"]([^>"]+)[>"]', re.M)
    _RE_CLASS   = re.compile(r'(?:class|struct)\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+([\w,\s:]+))?', re.M)
    _RE_FUNC    = re.compile(
        r'((?:[\w:*&<>\[\]]+\s+)+)(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:override)?\s*(?:noexcept)?\s*\{',
        re.M
    )
    _RE_NS      = re.compile(r'namespace\s+(\w+)\s*\{', re.M)
    _RE_TYPEDEF = re.compile(r'typedef\s+[\w\s*]+\s+(\w+)\s*;', re.M)
    _RE_USING   = re.compile(r'using\s+(\w+)\s*=', re.M)

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if root_path is None:
            root_path = os.getcwd()
        path = Path(file_path)
        nodes, edges, errors = [], [], []
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        lines    = source.splitlines()
        rel_file = str(path)
        mod_name = path.stem

        nodes.append({
            "name": mod_name, "type": "module",
            "file": rel_file, "language": self.LANGUAGE,
            "line_start": 1, "line_end": len(lines),
            "complexity": 0, "quality": 100.0,
            "signature": path.name, "docstring": "",
            "metadata": {"is_header": path.suffix in (".h", ".hpp", ".hxx")},
        })

        # Includes
        for m in self._RE_INCLUDE.finditer(source):
            dep    = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({"name": dep, "type": "dependency", "file": rel_file,
                           "language": self.LANGUAGE, "line_start": lineno, "line_end": lineno,
                           "complexity": 0, "quality": 100.0,
                           "signature": f"#include <{dep}>", "docstring": "", "metadata": {}})
            edges.append(self._edge(mod_name, rel_file, dep, rel_file, "imports", 5.0))

        # Namespaces
        for m in self._RE_NS.finditer(source):
            nsname = m.group(1)
            lineno = source[:m.start()].count("\n") + 1
            nodes.append({
                "name": nsname, "type": "module",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 100,
                "complexity": 0, "quality": 100.0,
                "signature": f"namespace {nsname}", "docstring": "", "metadata": {},
            })

        # Classes / Structs
        class_names = set()
        for m in self._RE_CLASS.finditer(source):
            cname, bases = m.groups()
            if cname in ("if", "else", "for", "while", "switch", "return"): continue
            class_names.add(cname)
            lineno = source[:m.start()].count("\n") + 1
            cx = self._cyclo(source[m.start():m.start() + 3000])
            nodes.append({
                "name": cname, "type": "class",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 50,
                "complexity": cx, "quality": 100.0,
                "signature": m.group(0).strip(),
                "docstring": self._doxygen(source, m.start()),
                "metadata": {"bases": bases.split(",") if bases else []},
            })
            edges.append(self._edge(mod_name, rel_file, cname, rel_file, "defines", 8.0))
            if bases:
                for base in bases.split(","):
                    base = base.strip().split()[-1]
                    if base:
                        edges.append(self._edge(cname, rel_file, base, rel_file, "inherits", 9.0))

        # Functions
        skip = {"if", "for", "while", "switch", "else", "return", "do", "namespace"}
        for m in self._RE_FUNC.finditer(source):
            ret_type = (m.group(1) or "").strip()
            fname    = m.group(2)
            params   = m.group(3) or ""
            if fname in skip or fname in class_names: continue
            lineno = source[:m.start()].count("\n") + 1
            cx = self._cyclo(source[m.start():m.start() + 1500])
            nodes.append({
                "name": fname, "type": "function",
                "file": rel_file, "language": self.LANGUAGE,
                "line_start": lineno, "line_end": lineno + 30,
                "complexity": cx, "quality": 100.0,
                "signature": f"{ret_type} {fname}({params})".strip(),
                "docstring": self._doxygen(source, m.start()),
                "metadata": {"params": params or ""},
            })
            edges.append(self._edge(mod_name, rel_file, fname, rel_file, "defines", 7.0))

        for node in nodes:
            if node["type"] not in ("module", "dependency"):
                node["quality"] = self._score(node)

        return {"nodes": nodes, "edges": edges, "errors": errors}

    def _doxygen(self, source: str, pos: int) -> str:
        before = source[max(0, pos - 300):pos]
        m = re.search(r'/\*\*?(.*?)\*/', before, re.DOTALL)
        if m:
            return re.sub(r'\s*\*\s?', ' ', m.group(1)).strip()
        # Single-line
        lines = before.strip().splitlines()
        doc_lines = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                doc_lines.insert(0, stripped[2:].strip())
            else:
                break
        return " ".join(doc_lines)

    def _cyclo(self, code: str) -> int:
        return min(1 + len(re.findall(
            r'\b(if|else|for|while|switch|case|&&|\|\||\?)\b', code
        )), 20)

    def _edge(self, fn, ff, tn, tf, rel, w) -> Dict:
        return {"from_name": fn, "from_file": ff, "to_name": tn, "to_file": tf,
                "relationship": rel, "weight": w}

    def _score(self, node: Dict) -> float:
        s = 100.0
        cx = node.get("complexity", 0)
        if cx > 10: s -= 30
        elif cx > 7: s -= 20
        elif cx > 5: s -= 10
        if not node.get("docstring") and node["type"] in ("function", "class"): s -= 8
        return max(0.0, min(100.0, s))