"""
AgentGraph Intelligence - Tree-sitter Language Configurations
All node type mappings, field names, and query patterns for 7 languages.
Adapted from Graphify's extract.py architecture.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple


@dataclass
class LanguageConfig:
    """
    Encapsulates everything tree-sitter needs to parse one language:
      - which tree-sitter module to import
      - which AST node types map to AgentGraph node types
      - which field names hold names / bodies / parameters
      - S-expression queries for extracting call edges (second pass)
    """
    name: str                              # canonical language name
    module: str                            # Python module: tree_sitter_python etc.
    extensions: Set[str]                   # file suffixes owned by this config

    # node_type -> agentgraph type  (class|function|method|interface|variable|dependency|module)
    node_type_map: Dict[str, str]

    # AST field that holds the symbol name inside each node type
    name_fields: Dict[str, str]            # node_type -> field name

    # Field that holds the body block (used to scope child search)
    body_fields: Dict[str, str]

    # Field that holds parameters
    param_fields: Dict[str, str]

    # Field that holds return type annotation (if any)
    return_fields: Dict[str, str]

    # Field that holds docstring / leading comment node type
    doc_node_types: Set[str]

    # S-expression patterns for call-graph second pass
    call_queries: List[str] = field(default_factory=list)

    # Import node types that map to "dependency" + "imports" edge
    import_node_types: Set[str] = field(default_factory=set)

    # Inheritance / implements node types -> relationship label
    inheritance_node_types: Dict[str, str] = field(default_factory=dict)

    # Weight assigned to edges by relationship type
    edge_weights: Dict[str, float] = field(default_factory=dict)

    def default_edge_weight(self, rel: str) -> float:
        return self.edge_weights.get(rel, 5.0)


# ─────────────────────────────────────────────────────────────────────────────
# PYTHON
# ─────────────────────────────────────────────────────────────────────────────

PYTHON_CONFIG = LanguageConfig(
    name       = "python",
    module     = "tree_sitter_python",
    extensions = {".py", ".pyw", ".pyi"},
    node_type_map = {
        "class_definition":           "class",
        "function_definition":        "function",
        "async_function_definition":  "function",
        "decorated_definition":       "function",   # resolved by child inspection
        "import_statement":           "dependency",
        "import_from_statement":      "dependency",
        "module":                     "module",
        "assignment":                 "variable",
        "augmented_assignment":       "variable",
        "annotated_assignment":       "variable",
    },
    name_fields = {
        "class_definition":           "name",
        "function_definition":        "name",
        "async_function_definition":  "name",
        "import_statement":           "name",
        "import_from_statement":      "name",
    },
    body_fields = {
        "class_definition":           "body",
        "function_definition":        "body",
        "async_function_definition":  "body",
    },
    param_fields = {
        "function_definition":        "parameters",
        "async_function_definition":  "parameters",
    },
    return_fields = {
        "function_definition":        "return_type",
        "async_function_definition":  "return_type",
    },
    doc_node_types      = {"expression_statement", "string"},
    import_node_types   = {"import_statement", "import_from_statement"},
    inheritance_node_types = {
        "argument_list": "inherits",    # class Foo(Base): argument_list holds bases
    },
    call_queries = [
        "(call function: (identifier) @callee)",
        "(call function: (attribute object: (_) @obj attribute: (identifier) @attr))",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    5.0,
        "inherits":   9.0,
        "implements": 8.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# JAVASCRIPT
# ─────────────────────────────────────────────────────────────────────────────

JAVASCRIPT_CONFIG = LanguageConfig(
    name       = "javascript",
    module     = "tree_sitter_javascript",
    extensions = {".js", ".jsx", ".mjs", ".cjs"},
    node_type_map = {
        "class_declaration":           "class",
        "class_expression":            "class",
        "function_declaration":        "function",
        "function_expression":         "function",
        "arrow_function":              "function",
        "method_definition":           "method",
        "generator_function_declaration": "function",
        # import_declaration, export_statement handled via import_node_types
        # call_expression handled in second pass
        "lexical_declaration":         "variable",
        "variable_declaration":        "variable",
        "program":                     "module",
    },
    name_fields = {
        "class_declaration":           "name",
        "function_declaration":        "name",
        "method_definition":           "name",
        # import_declaration name is handled via _extract_js_import
        "lexical_declaration":         "name",      # first declarator.name
    },
    body_fields = {
        "class_declaration":           "body",
        "function_declaration":        "body",
        "function_expression":         "body",
        "method_definition":           "body",
        "arrow_function":              "body",
    },
    param_fields = {
        "function_declaration":        "parameters",
        "function_expression":         "parameters",
        "method_definition":           "parameters",
        "arrow_function":              "parameters",
    },
    return_fields = {},
    doc_node_types      = {"comment"},
    import_node_types   = {"import_statement", "export_statement"},
    inheritance_node_types = {
        "class_heritage": "inherits",
    },
    call_queries = [
        "(call_expression function: (identifier) @callee)",
        "(call_expression function: (member_expression object: (_) @obj property: (property_identifier) @prop))",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    6.0,
        "inherits":   9.0,
        "implements": 8.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# TYPESCRIPT
# ─────────────────────────────────────────────────────────────────────────────

TYPESCRIPT_CONFIG = LanguageConfig(
    name       = "typescript",
    module     = "tree_sitter_typescript",
    extensions = {".ts", ".tsx"},
    node_type_map = {
        "class_declaration":                "class",
        "abstract_class_declaration":       "class",
        "interface_declaration":            "interface",
        "type_alias_declaration":           "variable",
        "enum_declaration":                 "variable",
        "function_declaration":             "function",
        "function_expression":              "function",
        "arrow_function":                   "function",
        "method_definition":                "method",
        "method_signature":                 "method",
        "public_field_definition":          "variable",
        "import_statement":                 "dependency",
        "export_statement":                 "dependency",
        "program":                          "module",
    },
    name_fields = {
        "class_declaration":                "name",
        "abstract_class_declaration":       "name",
        "interface_declaration":            "name",
        "type_alias_declaration":           "name",
        "enum_declaration":                 "name",
        "function_declaration":             "name",
        "method_definition":                "name",
        "method_signature":                 "name",
        "import_statement":                 "source",
    },
    body_fields = {
        "class_declaration":                "body",
        "abstract_class_declaration":       "body",
        "interface_declaration":            "body",
        "function_declaration":             "body",
        "method_definition":                "body",
    },
    param_fields = {
        "function_declaration":             "parameters",
        "function_expression":              "parameters",
        "method_definition":                "parameters",
        "arrow_function":                   "parameters",
    },
    return_fields = {
        "function_declaration":             "return_type",
        "method_definition":                "return_type",
        "method_signature":                 "return_type",
    },
    doc_node_types      = {"comment"},
    import_node_types   = {"import_statement"},
    inheritance_node_types = {
        "extends_clause":    "inherits",
        "implements_clause": "implements",
        "class_heritage":    "inherits",
    },
    call_queries = [
        "(call_expression function: (identifier) @callee)",
        "(call_expression function: (member_expression property: (property_identifier) @prop))",
        "(new_expression constructor: (identifier) @callee)",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    6.0,
        "inherits":   9.0,
        "implements": 8.0,
        "calls":      6.0,
        "extends":    9.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# JAVA
# ─────────────────────────────────────────────────────────────────────────────

JAVA_CONFIG = LanguageConfig(
    name       = "java",
    module     = "tree_sitter_java",
    extensions = {".java"},
    node_type_map = {
        "class_declaration":            "class",
        "enum_declaration":             "class",
        "record_declaration":           "class",
        "interface_declaration":        "interface",
        "annotation_type_declaration":  "interface",
        "method_declaration":           "method",
        "constructor_declaration":      "method",
        "import_declaration":           "dependency",
        "program":                      "module",
        "field_declaration":            "variable",
    },
    name_fields = {
        "class_declaration":            "name",
        "enum_declaration":             "name",
        "record_declaration":           "name",
        "interface_declaration":        "name",
        "method_declaration":           "name",
        "constructor_declaration":      "name",
        "import_declaration":           "name",
    },
    body_fields = {
        "class_declaration":            "body",
        "interface_declaration":        "body",
        "method_declaration":           "body",
        "constructor_declaration":      "body",
    },
    param_fields = {
        "method_declaration":           "formal_parameters",
        "constructor_declaration":      "formal_parameters",
    },
    return_fields = {
        "method_declaration":           "type",
    },
    doc_node_types      = {"block_comment", "line_comment"},
    import_node_types   = {"import_declaration"},
    inheritance_node_types = {
        "superclass":           "inherits",
        "super_interfaces":     "implements",
        "extends_interfaces":   "inherits",
    },
    call_queries = [
        "(method_invocation name: (identifier) @callee)",
        "(object_creation_expression type: (type_identifier) @callee)",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    5.0,
        "inherits":   9.0,
        "implements": 8.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# GO
# ─────────────────────────────────────────────────────────────────────────────

GO_CONFIG = LanguageConfig(
    name       = "go",
    module     = "tree_sitter_go",
    extensions = {".go"},
    node_type_map = {
        "type_declaration":           "class",      # struct → class
        "type_spec":                  "class",
        "struct_type":                "class",
        "interface_type":             "interface",
        "function_declaration":       "function",
        "method_declaration":         "method",
        "import_declaration":         "dependency",
        "import_spec":                "dependency",
        "source_file":                "module",
        "const_declaration":          "variable",
        "var_declaration":            "variable",
    },
    name_fields = {
        "type_spec":              "name",
        "function_declaration":   "name",
        "method_declaration":     "name",
        "import_spec":            "path",
    },
    body_fields = {
        "function_declaration":   "body",
        "method_declaration":     "body",
    },
    param_fields = {
        "function_declaration":   "parameters",
        "method_declaration":     "parameters",
    },
    return_fields = {
        "function_declaration":   "result",
        "method_declaration":     "result",
    },
    doc_node_types      = {"comment"},
    import_node_types   = {"import_declaration", "import_spec"},
    inheritance_node_types = {},    # Go has no inheritance; interface satisfaction is implicit
    call_queries = [
        "(call_expression function: (identifier) @callee)",
        "(call_expression function: (selector_expression field: (field_identifier) @callee))",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    5.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# RUST
# ─────────────────────────────────────────────────────────────────────────────

RUST_CONFIG = LanguageConfig(
    name       = "rust",
    module     = "tree_sitter_rust",
    extensions = {".rs"},
    node_type_map = {
        "struct_item":          "class",
        "enum_item":            "class",
        "union_item":           "class",
        "trait_item":           "interface",
        "impl_item":            "class",        # impl block groups methods
        "function_item":        "function",
        "use_declaration":      "dependency",
        "mod_item":             "module",
        "source_file":          "module",
        "const_item":           "variable",
        "static_item":          "variable",
        "type_item":            "variable",
    },
    name_fields = {
        "struct_item":          "name",
        "enum_item":            "name",
        "union_item":           "name",
        "trait_item":           "name",
        "impl_item":            "type",         # impl <Type> or impl <Trait> for <Type>
        "function_item":        "name",
        "mod_item":             "name",
        "const_item":           "name",
        "static_item":          "name",
        "type_item":            "name",
    },
    body_fields = {
        "struct_item":          "body",
        "trait_item":           "body",
        "impl_item":            "body",
        "function_item":        "body",
    },
    param_fields = {
        "function_item":        "parameters",
    },
    return_fields = {
        "function_item":        "return_type",
    },
    doc_node_types      = {"line_comment", "block_comment"},
    import_node_types   = {"use_declaration"},
    inheritance_node_types = {
        "impl_item": "implements",   # impl Trait for Type
    },
    call_queries = [
        "(call_expression function: (identifier) @callee)",
        "(call_expression function: (field_expression field: (field_identifier) @callee))",
        "(call_expression function: (scoped_identifier name: (identifier) @callee))",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    5.0,
        "implements": 9.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# C / C++
# ─────────────────────────────────────────────────────────────────────────────

CPP_CONFIG = LanguageConfig(
    name       = "cpp",
    module     = "tree_sitter_cpp",
    extensions = {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hxx"},
    node_type_map = {
        "class_specifier":              "class",
        "struct_specifier":             "class",
        "union_specifier":              "class",
        "function_definition":          "function",
        "function_declarator":          "function",
        "namespace_definition":         "module",
        "preproc_include":              "dependency",
        "declaration":                  "variable",
        "type_definition":              "variable",
        "translation_unit":             "module",
        "template_declaration":         "function",
    },
    name_fields = {
        "class_specifier":              "name",
        "struct_specifier":             "name",
        "union_specifier":              "name",
        "function_declarator":          "declarator",
        "namespace_definition":         "name",
        "preproc_include":              "path",
    },
    body_fields = {
        "class_specifier":              "body",
        "function_definition":          "body",
        "namespace_definition":         "body",
    },
    param_fields = {
        "function_declarator":          "parameters",
    },
    return_fields = {},
    doc_node_types      = {"comment"},
    import_node_types   = {"preproc_include"},
    inheritance_node_types = {
        "base_class_clause": "inherits",
    },
    call_queries = [
        "(call_expression function: (identifier) @callee)",
        "(call_expression function: (field_expression field: (field_identifier) @callee))",
        "(call_expression function: (qualified_identifier name: (identifier) @callee))",
    ],
    edge_weights = {
        "defines":    8.0,
        "imports":    5.0,
        "inherits":   9.0,
        "calls":      6.0,
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

ALL_CONFIGS: List[LanguageConfig] = [
    PYTHON_CONFIG,
    JAVASCRIPT_CONFIG,
    TYPESCRIPT_CONFIG,
    JAVA_CONFIG,
    GO_CONFIG,
    RUST_CONFIG,
    CPP_CONFIG,
]

# Extension -> config lookup
EXT_TO_CONFIG: Dict[str, LanguageConfig] = {}
for _cfg in ALL_CONFIGS:
    for _ext in _cfg.extensions:
        EXT_TO_CONFIG[_ext] = _cfg


def get_config(file_path: str) -> Optional[LanguageConfig]:
    from pathlib import Path
    return EXT_TO_CONFIG.get(Path(file_path).suffix.lower())