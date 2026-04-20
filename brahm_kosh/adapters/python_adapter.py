"""
Python AST Adapter for Brahm-Kosh.

Walks a directory tree, parses every .py file using the ast module,
and builds the universal code model.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Optional

from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


# Directories to always skip
SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "*.egg-info",
}


def should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    if dirname.startswith("."):
        return True
    if dirname in SKIP_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


class CallExtractor(ast.NodeVisitor):
    """Extracts function/method call names from an AST node."""

    def __init__(self):
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


class ComplexityCounter(ast.NodeVisitor):
    """Counts branching statements and max nesting depth in an AST node."""

    def __init__(self):
        self.branch_count = 0
        self.max_depth = 0
        self._current_depth = 0

    def _enter_branch(self, node: ast.AST) -> None:
        self.branch_count += 1
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1

    def visit_If(self, node: ast.If) -> None:
        self._enter_branch(node)

    def visit_For(self, node: ast.For) -> None:
        self._enter_branch(node)

    def visit_While(self, node: ast.While) -> None:
        self._enter_branch(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._enter_branch(node)

    def visit_TryStar(self, node: ast.AST) -> None:
        self._enter_branch(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._enter_branch(node)

    def visit_With(self, node: ast.With) -> None:
        self._enter_branch(node)

    def visit_Match(self, node: ast.AST) -> None:
        self._enter_branch(node)


def _get_docstring(node: ast.AST) -> Optional[str]:
    """Extract docstring from a function or class node."""
    try:
        return ast.get_docstring(node)
    except TypeError:
        return None


def _parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef, kind: SymbolKind) -> Symbol:
    """Parse a function/method AST node into a Symbol."""
    # Extract calls
    call_extractor = CallExtractor()
    call_extractor.visit(node)

    # Count complexity
    complexity_counter = ComplexityCounter()
    complexity_counter.visit(node)

    return Symbol(
        name=node.name,
        kind=kind,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        docstring=_get_docstring(node),
        calls=list(set(call_extractor.calls)),
        children=[],
        nesting_depth=complexity_counter.max_depth,
        branch_count=complexity_counter.branch_count,
    )


def _parse_class(node: ast.ClassDef) -> Symbol:
    """Parse a class AST node into a Symbol with methods as children."""
    methods = []
    for item in ast.iter_child_nodes(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_parse_function(item, SymbolKind.METHOD))

    # Class-level complexity
    complexity_counter = ComplexityCounter()
    complexity_counter.visit(node)

    return Symbol(
        name=node.name,
        kind=SymbolKind.CLASS,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        docstring=_get_docstring(node),
        calls=[],
        children=methods,
        nesting_depth=complexity_counter.max_depth,
        branch_count=complexity_counter.branch_count,
    )


def parse_file(file_path: str, project_root: str) -> Optional[FileModel]:
    """
    Parse a single Python file into a FileModel.

    Returns None if the file cannot be parsed.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError) as e:
        rel_path = os.path.relpath(file_path, project_root)
        return FileModel(
            name=os.path.basename(file_path),
            path=file_path,
            relative_path=rel_path,
            line_count=0,
            symbols=[],
            purpose="⚠️ IO Error",
            language="Python",
        )

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        # Still count lines even if we can't parse
        lines = source.count("\n") + 1
        rel_path = os.path.relpath(file_path, project_root)
        return FileModel(
            name=os.path.basename(file_path),
            path=file_path,
            relative_path=rel_path,
            line_count=lines,
            symbols=[],
            purpose="⚠️ Syntax Error",
            language="Python",
        )

    lines = source.count("\n") + 1
    rel_path = os.path.relpath(file_path, project_root)

    symbols: list[Symbol] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(_parse_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_parse_function(node, SymbolKind.FUNCTION))

    return FileModel(
        name=os.path.basename(file_path),
        path=file_path,
        relative_path=rel_path,
        line_count=lines,
        symbols=symbols,
        language="Python",
    )


def analyze_directory(root_path: str) -> Project:
    """
    Walk a directory tree and build the full Project model.

    This is the main entry point for the Python adapter.
    """
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)

    # Collect all Python files organized by directory
    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out dirs we should skip (modifying in-place controls os.walk)
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        py_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if f.endswith(".py")
        ])

        if py_files:
            dir_files[dirpath] = py_files

    # Build modules from directories
    modules: list[Module] = []
    root_files: list[FileModel] = []

    # Track which directories are modules (contain __init__.py or .py files)
    module_map: dict[str, Module] = {}

    for dirpath in sorted(dir_files.keys()):
        parsed_files = []
        for fpath in dir_files[dirpath]:
            fm = parse_file(fpath, root_path)
            if fm:
                parsed_files.append(fm)

        if dirpath == root_path:
            root_files = parsed_files
        else:
            rel_path = os.path.relpath(dirpath, root_path)
            module = Module(
                name=os.path.basename(dirpath),
                path=dirpath,
                relative_path=rel_path,
                files=parsed_files,
            )
            module_map[dirpath] = module

    # Build module hierarchy
    for dirpath, module in sorted(module_map.items()):
        parent_path = os.path.dirname(dirpath)
        if parent_path in module_map:
            module_map[parent_path].submodules.append(module)
        else:
            modules.append(module)

    project = Project(
        name=project_name,
        path=root_path,
        modules=modules,
        root_files=root_files,
    )

    project.metadata.languages = ["Python"]

    return project

# Self-register the adapter upon import with supported extensions
from brahm_kosh.adapters.registry import register_adapter
register_adapter("python", analyze_directory, extensions=["py"])
