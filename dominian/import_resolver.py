"""
AgentGraph Intelligence - Universal Import Resolver
Resolves import strings to actual file/directory paths on disk,
enabling fully connected cross-file graphs.
"""

import os
from pathlib import Path
from typing import Optional


def resolve_js_import(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a JavaScript/TypeScript import to a file path."""
    if import_str.startswith('.'):
        base = Path(current_file).parent
        # Handle both './lib' and './lib.js' style imports
        resolved = (base / import_str).resolve()

        # If import_str already has an extension, check it directly
        if Path(import_str).suffix:
            if resolved.exists() and resolved.is_file():
                return str(resolved)
            return None

        # Try adding extensions
        for ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'):
            candidate = resolved.with_suffix(ext)
            if candidate.exists() and candidate.is_file():
                return str(candidate)
            # Also try as directory with index file
            index_candidate = resolved / ('index' + ext)
            if index_candidate.exists() and index_candidate.is_file():
                return str(index_candidate)
        return None
    return None


def resolve_java_import(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a Java import to a .java file under the project root."""
    parts = import_str.split('.')
    path = str(Path(project_root).joinpath(*parts)) + '.java'
    if os.path.exists(path):
        return path
    path = str(Path(project_root) / 'src' / 'main' / 'java' / Path(*parts).with_suffix('.java'))
    if os.path.exists(path):
        return path
    return None


def resolve_go_import(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a Go import to a directory containing .go files."""
    if import_str.startswith('.'):
        base = Path(current_file).parent
        target = (base / import_str).resolve()
        if target.is_dir() and any(target.glob('*.go')):
            return str(target)
        return None
    return None


def resolve_rust_use(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a Rust use declaration to a file path."""
    if import_str.startswith('crate::'):
        parts = import_str[6:].split('::')
        src_dir = Path(project_root) / 'src'
        if src_dir.exists():
            candidate = src_dir.joinpath(*parts).with_suffix('.rs')
            if candidate.exists():
                return str(candidate)
            candidate = src_dir.joinpath(*parts, 'mod.rs')
            if candidate.exists():
                return str(candidate)
        return None
    elif import_str.startswith('self::') or import_str.startswith('super::'):
        base = Path(current_file).parent
        resolved = (base / import_str.replace('::', '/')).with_suffix('.rs')
        if resolved.exists():
            return str(resolved)
        return None
    return None


def resolve_cpp_include(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a C/C++ #include to a header file."""
    if import_str.startswith('<'):
        return None
    base = Path(current_file).parent
    candidate = base / import_str
    if candidate.exists():
        return str(candidate)
    for inc_dir in ['include', 'inc', 'src']:
        candidate = Path(project_root) / inc_dir / import_str
        if candidate.exists():
            return str(candidate)
    return None


def resolve_python_import(import_str: str, current_file: str, project_root: str) -> Optional[str]:
    """Resolve a Python import to a .py file."""
    from pathlib import Path

    # Clean up import string
    import_str = import_str.strip().rstrip(';').strip('"').strip("'")
    if not import_str:
        return None

    current_dir = Path(current_file).parent

    # Handle relative imports
    if import_str.startswith('.'):
        parts = import_str.lstrip('.').split('.')
        target_dir = current_dir
        # Go up one level for each leading dot beyond the first
        dots = len(import_str) - len(import_str.lstrip('.'))
        for _ in range(dots - 1):
            target_dir = target_dir.parent

        for part in parts:
            if part:
                target_dir = target_dir / part

        # Try as file
        candidate = target_dir.with_suffix('.py')
        if candidate.exists():
            return str(candidate)
        # Try as package
        candidate = target_dir / '__init__.py'
        if candidate.exists():
            return str(candidate)
        return None

    # Handle absolute imports - convert dots to path
    parts = import_str.split('.')

    # Try in current directory first
    candidate = current_dir / Path(*parts).with_suffix('.py')
    if candidate.exists():
        return str(candidate)
    candidate = current_dir / Path(*parts) / '__init__.py'
    if candidate.exists():
        return str(candidate)

    # Try in project root
    project_path = Path(project_root)
    candidate = project_path / Path(*parts).with_suffix('.py')
    if candidate.exists():
        return str(candidate)
    candidate = project_path / Path(*parts) / '__init__.py'
    if candidate.exists():
        return str(candidate)

    # Try src/ prefix (common layout)
    candidate = project_path / 'src' / Path(*parts).with_suffix('.py')
    if candidate.exists():
        return str(candidate)

    return None


def resolve_import_to_file(import_str: str, current_file: str, language: str, project_root: str) -> Optional[str]:
    """Resolve an import string to an actual file path, using language rules."""
    import_str = import_str.strip().rstrip(';').strip('"').strip("'")
    if not import_str:
        return None

    lang = language.lower()
    if lang in ('python', 'py'):
        return resolve_python_import(import_str, current_file, project_root)
    elif lang in ('javascript', 'typescript', 'js', 'ts', 'jsx', 'tsx'):
        return resolve_js_import(import_str, current_file, project_root)
    elif lang == 'java':
        return resolve_java_import(import_str, current_file, project_root)
    elif lang == 'go':
        return resolve_go_import(import_str, current_file, project_root)
    elif lang == 'rust':
        return resolve_rust_use(import_str, current_file, project_root)
    elif lang in ('cpp', 'c', 'c++'):
        return resolve_cpp_include(import_str, current_file, project_root)
    return None
