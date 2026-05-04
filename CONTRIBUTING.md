# Contributing to Dominian

Thank you for your interest in contributing to Dominian. This document covers everything you need to know to get started.

---

## Code of Conduct

Be respectful. Be constructive. Be specific. We are all here to make code intelligence better for agents and humans alike.

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- A terminal

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/dominian.git
cd dominian

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode with all dependencies
pip install -e ".[all]"

# Install development tools
pip install pytest ruff mypy
```

### Project Structure

```
dominian/
├── __init__.py              # ParserRegistry, CodebaseScanner, GlobalConfig
├── main_new.py              # CLI entry point (argparse)
├── server.py                # MCP server (FastMCP)
├── database.py              # GraphDatabase (SQLite + WAL)
├── engine.py                # QueryEngine (intent resolution)
├── formatter.py             # Output formatting (minimal, agent, json)
├── adaptive_scanner.py      # Adaptive multi-strategy scanner
├── tree_sitter_parser.py    # Tree-sitter parser wrapper
├── tree_sitter_configs.py   # Language configurations (7 languages)
├── import_resolver.py       # Cross-file import resolution
├── python_parser.py         # Python regex parser
├── javascript_parser.py     # JavaScript/TypeScript regex parser
├── other_parsers.py         # Java, Go, Rust, C++ regex parsers
├── ast_walker.py            # AST walking for tree-sitter
└── tests/
    ├── test_database.py
    ├── test_scanner.py
    ├── test_formatter.py
    └── ...
```

---

## How to Contribute

### Reporting Bugs

1. Check if the bug is already reported in [GitHub Issues](../../issues).
2. If not, open a new issue with:
   - **Reproduction steps**: Exact commands to reproduce.
   - **Expected behavior**: What should happen.
   - **Actual behavior**: What actually happens.
   - **Environment**: OS, Python version, Dominian version.
   - **Codebase**: Language and approximate size of the scanned project.

### Suggesting Features

1. Open a [GitHub Issue](../../issues) with the `enhancement` label.
2. Describe the use case: what problem does this solve for agents or humans?
3. If possible, suggest the CLI command or MCP tool name.
4. Consider token efficiency: will the output be compact enough for agent consumption?

### Submitting Pull Requests

1. **Fork** the repository and create your branch from `main`.
2. **Write code** following the style guidelines below.
3. **Test** your changes locally.
4. **Document** any new CLI commands, MCP tools, or output format changes.
5. **Submit** the PR with a clear description.

#### PR Checklist

- [ ] Code follows project style (see below)
- [ ] New functionality includes tests
- [ ] Documentation updated if needed (README, API_REFERENCE, AGENT_GUIDE)
- [ ] No breaking changes to existing CLI commands or MCP tools without discussion
- [ ] Output format changes preserve token efficiency
- [ ] `pragma: no cover` only used with justification

---

## Code Style

### General Rules

- **Python 3.10+**: Use `X | Y` union syntax, `match/case` where appropriate.
- **Type hints**: All public functions must have type annotations.
- **Docstrings**: All public functions, classes, and modules must have docstrings.
- **Line length**: 100 characters maximum.
- **Imports**: Standard library, then third-party, then local. One blank line between groups.

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | snake_case | `adaptive_scanner.py` |
| Classes | PascalCase | `GraphDatabase`, `AdaptiveScanner` |
| Functions | snake_case | `get_dependencies()`, `find_cycles()` |
| Constants | UPPER_SNAKE | `DB_PATH`, `IGNORE_DIRS` |
| CLI commands | snake_case subcommands | `dominian deps direct` |
| MCP tools | `dominian_{group}_{action}` | `dominian_deps_direct` |

### Output Format Rules

When adding new output to the formatter:

1. **Always add minimal format first**. The minimal format is the default and the one agents use. Every character must earn its place.
2. **Use the locator syntax**: `folder/file:name:line(type)` for referencing entities.
3. **Use type abbreviations**: `fn` (function/method), `cls` (class), `mod` (module), `var` (variable), `imp` (import/dependency).
4. **Use Unicode symbols sparingly**: Only for semantic markers (`📥` deps, `📤` dependents, `⚠️` impact, `✅` safe, `🚫` unsafe, `📍` location, `🔍` search, `🔥` hotspot, `🔄` cycle, `📦` community, `🔗` cross-community, `📄` file).
5. **Pipe separator** (`|`) between items in a list. Comma separator between fields within an item.
6. **Count first, then details**: `5:entity1,entity2,...` rather than listing then counting.

### Database Rules

1. **Always use batch operations** for inserting nodes/edges during scans: `upsert_nodes_batch()` and `upsert_edges_batch()`.
2. **Node IDs are `{file}::{name}`** — never change this format.
3. **Edge IDs are `{from_id}--{relationship}--{to_id}`** — never change this format.
4. **New columns must have defaults** — existing databases must continue to work without migration scripts.
5. **Use `ON CONFLICT ... DO UPDATE`** for upserts, never raw `INSERT OR REPLACE` which drops columns not specified.

### Adding a New Parser

1. Create a new parser class in the appropriate file with `LANGUAGE` and `EXTENSIONS` class attributes.
2. Implement `parse(file_path: str, root_path: Optional[str] = None) -> Dict` returning `{"nodes": [...], "edges": [...], "errors": [...]}`.
3. Add a `LanguageConfig` in `tree_sitter_configs.py` if tree-sitter support is desired.
4. Register the parser in `ParserRegistry.init_all()` inside `__init__.py`.
5. Add import resolution in `import_resolver.py` if the language has non-trivial import paths.
6. Add tests in `tests/`.

### Adding a New MCP Tool

1. Add the tool function in `server.py` with the `@mcp.tool()` decorator.
2. Use the naming convention `dominian_{group}_{action}`.
3. Include a comprehensive docstring — it becomes the tool description visible to the LLM.
4. Return minimal format output via `_minimal()`.
5. Add the tool to the README.md MCP Tools table.
6. Add the tool to docs/API_REFERENCE.md.
7. Add usage examples to docs/AGENT_GUIDE.md.

### Adding a New CLI Command

1. Add the command implementation function in `main_new.py` following the `cmd_{name}` pattern.
2. Register it in the argparse structure in `main()`.
3. Add formatter support in `formatter.py` if needed (both `format_minimal` and `format_for_claude`).
4. Add the command to README.md CLI Reference table.
5. Add the command to docs/API_REFERENCE.md.

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_database.py -v

# Run with coverage
pytest --cov=dominian --cov-report=term-missing
```

### Writing Tests

- **Unit tests**: Test individual functions and classes in isolation.
- **Integration tests**: Test CLI commands end-to-end using `subprocess.run()`.
- **Fixtures**: Use `tmp_path` for temporary databases. Never write to the project's own `.dominian/` directory.
- **Database tests**: Always close database connections after tests.

```python
# Example test
def test_search_nodes_returns_matching_results(tmp_path):
    db = GraphDatabase(str(tmp_path / "test.db"))
    db.upsert_node("handle_request", "function", "server.py", "python",
                    line_start=10, line_end=50)
    results = db.search_nodes("handle")
    assert len(results) == 1
    assert results[0]["name"] == "handle_request"
    db.close()
```

---

## Release Process

1. Update `VERSION` in `main_new.py` and `server.py`.
2. Update `CHANGELOG.md` with the new version entry.
3. Update `pyproject.toml` version if applicable.
4. Create a git tag: `git tag v1.x.x`.
5. Push tag: `git push origin v1.x.x`.
6. GitHub Actions will build and publish to PyPI.

---

## Questions?

Open a [GitHub Discussion](../../discussions) or join our community. We are happy to help.
