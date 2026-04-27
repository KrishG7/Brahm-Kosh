"""
Symbol-level Impact Analysis (Python only — for now).

File-level impact tells you "if you change models.py, 32 files might break."
That's the upper bound — every file that imports models.py *for any reason*.

This module answers the precise version: "if you rename the class
`FileModel` specifically, only 4 files actually reference it."

The technique is AST-based name tracking:
  1. For each Python file, walk the AST recording its `from X import Y as Z`
     and `import X as M` statements.
  2. Track which local names refer to project-defined symbols.
  3. Walk every Name and Attribute node in the file and record references
     to those tracked names.
  4. Index the whole project: `(defining_file, symbol) -> [(file, line), ...]`.

This is Python-only because the regex parsers used for the other 12
languages can't reliably distinguish a function call from a constructor
from an attribute access. Without that distinction, symbol resolution
returns garbage. For Python we have the standard library `ast` module,
so we get this for free.

Limitations (deliberate, documented):
  - Does NOT track instance attribute access (`fm.complexity`) — that
    needs type inference.
  - Re-exports aren't followed across modules.
  - `__all__` and `*`-imports are ignored.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass

from brahm_kosh.models import Project, SymbolKind


# ---------------------------------------------------------------------------
# Build a project-wide map: (file_path, symbol_name) -> list of usage sites
# ---------------------------------------------------------------------------

@dataclass
class SymbolUsage:
    file: str
    line: int

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line}


def _module_to_relpath(module: str, files_by_rel: dict[str, object]) -> str | None:
    """`brahm_kosh.models` -> `brahm_kosh/models.py` if that file exists."""
    if not module:
        return None
    candidate = module.replace(".", "/") + ".py"
    if candidate in files_by_rel:
        return candidate
    # Package init form
    pkg_init = module.replace(".", "/") + "/__init__.py"
    if pkg_init in files_by_rel:
        return pkg_init
    return None


def _resolve_relative_import(level: int, module: str, current_rel: str,
                             files_by_rel: dict[str, object]) -> str | None:
    """Translate `from . import x` style imports into a project file."""
    if level <= 0:
        return None
    cur_dir = os.path.dirname(current_rel)
    # Each `.` after the first walks up one directory
    for _ in range(level - 1):
        cur_dir = os.path.dirname(cur_dir)
    target = cur_dir
    if module:
        target = os.path.join(target, module.replace(".", "/")) if target else module.replace(".", "/")
    candidate = (target + ".py").replace("\\", "/").lstrip("/")
    if candidate in files_by_rel:
        return candidate
    pkg_init = (target.rstrip("/") + "/__init__.py").lstrip("/")
    if pkg_init in files_by_rel:
        return pkg_init
    return None


def build_symbol_usage_index(project: Project) -> dict[str, list[SymbolUsage]]:
    """
    Build the project-wide symbol usage index.

    Key format: `<defining_file_relpath>:<symbol_name>`
    """
    py_files = [fm for fm in project.all_files() if fm.language == "Python"]
    files_by_rel = {fm.relative_path: fm for fm in py_files}

    # Map: symbol_name -> list of (defining_file, Symbol)
    # Used for resolving bare-name references via wildcard tables.
    defs_by_name: dict[str, list[tuple[str, object]]] = {}
    for fm in py_files:
        for sym in fm.symbols:
            if sym.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
                defs_by_name.setdefault(sym.name, []).append((fm.relative_path, sym))

    usage_index: dict[str, list[SymbolUsage]] = {}

    for fm in py_files:
        try:
            with open(fm.path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=fm.path)
        except (OSError, SyntaxError):
            continue

        # local_name -> (defining_file, defining_symbol_name)
        imported_names: dict[str, tuple[str, str]] = {}
        # local_name -> defining_file_relpath  (for `import X as Y` style)
        module_aliases: dict[str, str] = {}

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    target_file = _resolve_relative_import(
                        node.level, node.module or "", fm.relative_path, files_by_rel
                    )
                else:
                    target_file = _module_to_relpath(node.module or "", files_by_rel)
                if target_file is None:
                    continue
                target_fm = files_by_rel[target_file]
                local_defs = {s.name for s in target_fm.symbols
                              if s.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION)}
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    if alias.name in local_defs:
                        imported_names[local] = (target_file, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    target_file = _module_to_relpath(alias.name, files_by_rel)
                    if target_file is None:
                        continue
                    local = alias.asname or alias.name.split(".")[0]
                    module_aliases[local] = target_file

        # Build a quick lookup of which symbols each module exposes
        exposed: dict[str, set[str]] = {}
        for path, file_obj in files_by_rel.items():
            exposed[path] = {s.name for s in file_obj.symbols
                             if s.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION)}

        # Walk all expressions for usages
        for node in ast.walk(tree):
            # Bare name: `FileModel(...)` after `from models import FileModel`
            if isinstance(node, ast.Name):
                if node.id in imported_names:
                    defining_file, defining_sym = imported_names[node.id]
                    if defining_file == fm.relative_path:
                        continue
                    key = f"{defining_file}:{defining_sym}"
                    usage_index.setdefault(key, []).append(
                        SymbolUsage(file=fm.relative_path, line=node.lineno)
                    )
            # Attribute on an imported module: `models.FileModel`
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id in module_aliases:
                    target_file = module_aliases[node.value.id]
                    if node.attr in exposed.get(target_file, set()):
                        if target_file == fm.relative_path:
                            continue
                        key = f"{target_file}:{node.attr}"
                        usage_index.setdefault(key, []).append(
                            SymbolUsage(file=fm.relative_path, line=node.lineno)
                        )

    return usage_index


# ---------------------------------------------------------------------------
# Per-symbol queries
# ---------------------------------------------------------------------------

def compute_symbol_impact(
    file_path: str,
    symbol_name: str,
    index: dict[str, list[SymbolUsage]],
) -> dict:
    """
    Resolve `<file>:<symbol>` to its full usage report.

    Returns a JSON-friendly payload listing every site that references
    the symbol, plus a summary of how many distinct files are affected.
    """
    key = f"{file_path}:{symbol_name}"
    usages = index.get(key, [])
    files = sorted(set(u.file for u in usages))
    return {
        "symbol": symbol_name,
        "defined_in": file_path,
        "usage_count": len(usages),
        "file_count": len(files),
        "files": files,
        "usages": [u.to_dict() for u in
                   sorted(usages, key=lambda u: (u.file, u.line))],
    }


def per_file_symbol_counts(
    file_path: str,
    file_symbols: list,
    index: dict[str, list[SymbolUsage]],
) -> dict[str, int]:
    """
    For each top-level symbol in `file_path`, return the count of distinct
    files that reference it. Used to decorate the Symbols sidebar.
    """
    out: dict[str, int] = {}
    for sym in file_symbols:
        if sym.kind not in (SymbolKind.CLASS, SymbolKind.FUNCTION):
            continue
        key = f"{file_path}:{sym.name}"
        files = {u.file for u in index.get(key, [])}
        out[sym.name] = len(files)
    return out
