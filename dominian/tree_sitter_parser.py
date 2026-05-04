"""
AgentGraph Intelligence - Tree-sitter Parser
Wraps tree-sitter for deterministic, language-agnostic parsing.
Auto-detects tree-sitter version (0.20.x or 0.22.x) and adapts.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from . import tree_sitter_configs
from .tree_sitter_configs import LanguageConfig


# ── Version detection ─────────────────────────────────────────────

_TS_VERSION = None
_ts_mod = None


def _detect_ts_version():
    global _TS_VERSION, _ts_mod
    if _TS_VERSION is not None:
        return _TS_VERSION
    try:
        ts = importlib.import_module("tree_sitter")
        _ts_mod = ts
        ver = getattr(ts, "__version__", "0.0.0")
        major = int(ver.split(".")[0])
        minor = int(ver.split(".")[1]) if len(ver.split(".")) > 1 else 0
        _TS_VERSION = (major, minor)
    except Exception:
        _TS_VERSION = (0, 0)
    return _TS_VERSION


_TS_REGISTRY_AVAILABLE = False


def get_global_registry() -> Dict[str, "TreeSitterParser"]:
    global _TS_REGISTRY_AVAILABLE
    try:
        from tree_sitter_parser import TreeSitterRegistry
        reg = TreeSitterRegistry()
        _TS_REGISTRY_AVAILABLE = True
        return reg.parsers
    except Exception:
        _TS_REGISTRY_AVAILABLE = False
        return {}


# ── Language loader ─────────────────────────────────────────────

def _load_ts_language(lang_name: str):
    """Load tree-sitter Language object for a given language."""
    try:
        import tree_sitter
    except ImportError:
        return None

    ver = _detect_ts_version()

    # Map language names to import paths
    lang_modules = {
        "python":     "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "tsx":        "tree_sitter_typescript",
        "java":       "tree_sitter_java",
        "go":         "tree_sitter_go",
        "rust":       "tree_sitter_rust",
        "cpp":        "tree_sitter_cpp",
        "c":          "tree_sitter_c",
        "c_sharp":    "tree_sitter_c_sharp",
    }

    module_name = lang_modules.get(lang_name, f"tree_sitter_{lang_name}")

    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        return None

    # Try different API versions
    try:
        if ver >= (0, 22):
            # tree-sitter 0.22+ API
            try:
                return tree_sitter.Language(mod.language())
            except AttributeError:
                return tree_sitter.Language(mod.language)
        else:
            # tree-sitter 0.20.x API
            return tree_sitter.Language(mod.language(), lang_name)
    except Exception:
        return None


# ── Parser ────────────────────────────────────────────────────────

class TreeSitterParser:
    """
    Language-agnostic parser using tree-sitter.
    Uses two-pass AST walking (structural + call-graph).
    """

    def __init__(self, config: LanguageConfig, extensions: Optional[Set[str]] = None):
        self.config     = config
        self.language   = config.name
        self.extensions = extensions or set(config.extensions)
        self.LANGUAGE   = config.name
        self.EXTENSIONS = self.extensions

        self._parser    = None
        self._ts_lang   = None
        self._init_done = False
        self._ts_ready  = False

    def parse(self, file_path: str, root_path: Optional[str] = None) -> Dict[str, Any]:
        if not self._lazy_init():
            return {"nodes": [], "edges": [], "errors": ["Tree-sitter not available"]}

        try:
            source_bytes = Path(file_path).read_bytes()
        except Exception as e:
            return {"nodes": [], "edges": [], "errors": [str(e)]}

        tree = self._parser.parse(source_bytes)
        if tree is None:
            return {"nodes": [], "edges": [], "errors": ["Parse failed"]}

        root = tree.root_node
        # Safe has_error check (not available in all tree-sitter versions)
        has_error = getattr(root, "has_error", False)
        if has_error:
            # Continue anyway — partial AST is still useful
            pass

        # Two-pass walk
        from ast_walker import ASTWalker, extract_call_edges

        walker = ASTWalker(self.config, file_path, source_bytes, project_root=root_path or os.getcwd())
        nodes, edges = walker.walk(root)

        # Pass 2: call-graph extraction
        if self._ts_lang:
            try:
                call_edges = extract_call_edges(
                    self._ts_lang, root, source_bytes, self.config,
                    {n["name"]: n for n in nodes if n["type"] in ("function", "method")},
                    file_path,
                )
                edges.extend(call_edges)
            except Exception:
                pass

        errors = ["Parse errors in file"] if has_error else []
        return {"nodes": nodes, "edges": edges, "errors": errors}

    # ── Lazy init ───────────────────────────────────────────────

    def _lazy_init(self) -> bool:
        if self._init_done:
            return self._ts_ready
        self._init_done = True

        try:
            import tree_sitter
        except ImportError:
            self._ts_ready = False
            return False

        self._ts_lang = _load_ts_language(self.language)
        if not self._ts_lang:
            self._ts_ready = False
            return False

        try:
            ver = _detect_ts_version()
            if ver >= (0, 22):
                self._parser = tree_sitter.Parser(self._ts_lang)
            else:
                self._parser = tree_sitter.Parser()
                self._parser.set_language(self._ts_lang)
            self._ts_ready = True
            return True
        except Exception:
            self._ts_ready = False
            return False


# ── Registry ─────────────────────────────────────────────────────

class TreeSitterRegistry:
    """
    Auto-detects installed tree-sitter languages and registers parsers.
    """

    def __init__(self):
        self.parsers: Dict[str, TreeSitterParser] = {}
        self._init_all()

    def _init_all(self):
        configs = tree_sitter_configs.ALL_CONFIGS
        for config in configs:
            ext_map = {
                "python":     {".py", ".pyw", ".pyi"},
                "javascript": {".js", ".jsx", ".mjs", ".cjs"},
                "typescript": {".ts", ".tsx"},
                "tsx":        {".tsx"},
                "java":       {".java"},
                "go":         {".go"},
                "rust":       {".rs"},
                "cpp":        {".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"},
                "c":          {".c", ".h"},
                "c_sharp":    {".cs"},
            }
            exts = ext_map.get(config.name, set(config.extensions))
            self.parsers[config.name] = TreeSitterParser(config, extensions=exts)
