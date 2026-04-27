"""
Rust Adapter for Brahm-Kosh.

Parses .rs files using pure-Python regex analysis.
Extracts:
  - Struct/Enum declarations
  - fn declarations (including inside impl blocks)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from brahm_kosh.parse_cache import memoize_by_mtime
from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


SKIP_DIRS = {
    ".git", "target", "vendor",
}

RUST_EXTENSIONS = {".rs"}


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


# Regex patterns
_RE_STRUCT_DECL = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]+\))?\s+)?(?:struct|enum|trait)\s+(\w+)",
    re.MULTILINE,
)

_RE_FUNC_DECL = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:const\s+)?fn\s+(\w+)\s*<[^>]*>?\s*\(",
    re.MULTILINE,
)
# simpler fallback for normal functions
_RE_FUNC_DECL_SIMPLE = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:const\s+)?fn\s+(\w+)\s*\(",
    re.MULTILINE,
)

_RE_BRANCH = re.compile(
    r"\b(if|else\s+if|for|while|loop|match)\b",
    re.MULTILINE,
)

# `use foo::bar::Baz;` and `mod foo;` — Rust's mod layout is complex, so
# this is best-effort. The resolver does a basename lookup and drops what
# doesn't exist in the project.
_RE_USE = re.compile(r"^\s*(?:pub\s+)?use\s+([\w:]+)", re.MULTILINE)
_RE_MOD = re.compile(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;", re.MULTILINE)


def _extract_imports(source: str) -> list[str]:
    found: list[str] = []
    for raw in _RE_USE.findall(source):
        parts = [p for p in raw.split("::") if p and p not in ("crate", "self", "super")]
        if parts and parts[0] not in ("std", "core", "alloc"):
            found.append("/".join(parts))
    found.extend(_RE_MOD.findall(source))
    return found


_RE_CALL = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

_KEYWORDS = {
    "if", "for", "while", "loop", "match", "return", "let", "mut",
    "pub", "fn", "struct", "enum", "trait", "impl", "use", "crate", "mod",
    "super", "self", "Self", "where", "async", "await", "break", "continue"
}


def _find_block_end(lines: list[str], start: int) -> int:
    depth = 0
    found_open = False
    for i in range(start, len(lines)):
        opens = lines[i].count("{")
        closes = lines[i].count("}")
        depth += opens - closes
        if opens > 0:
            found_open = True
        if found_open and depth <= 0:
            return i
    return len(lines) - 1


def _count_nesting_depth(lines: list[str]) -> int:
    depth = 0
    max_depth = 0
    for line in lines:
        depth += line.count("{") - line.count("}")
        depth = max(depth, 0)
        max_depth = max(max_depth, depth)
    return max_depth


def _count_branches(source: str) -> int:
    return len(_RE_BRANCH.findall(source))


def _extract_calls(source: str) -> list[str]:
    calls = _RE_CALL.findall(source)
    return list({c for c in calls if c not in _KEYWORDS})


def _score_symbol(line_count: int, nesting: int, branches: int, calls: int):
    from brahm_kosh.analysis.complexity import (
        MAX_BRANCHES, MAX_CALLS, MAX_LINES, MAX_NESTING,
        WEIGHT_BRANCHES, WEIGHT_CALLS, WEIGHT_LINES, WEIGHT_NESTING,
        _clamp,
    )
    raw = (
        WEIGHT_LINES * min(line_count / MAX_LINES, 1.0) * 100
        + WEIGHT_NESTING * min(nesting / MAX_NESTING, 1.0) * 100
        + WEIGHT_BRANCHES * min(branches / MAX_BRANCHES, 1.0) * 100
        + WEIGHT_CALLS * min(calls / MAX_CALLS, 1.0) * 100
    )
    return _clamp(raw), nesting, branches


def _parse_symbols(source: str, lines: list[str]) -> list[Symbol]:
    symbols: list[Symbol] = []

    for m in _RE_STRUCT_DECL.finditer(source):
        name = m.group(1)
        start_line = source[:m.start()].count("\n")
        end_line = _find_block_end(lines, start_line)
        body_lines = lines[start_line: end_line + 1]
        body = "\n".join(body_lines)
        
        lc = end_line - start_line + 1
        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        complexity, nd, bc = _score_symbol(lc, nesting, branches, 0)

        symbols.append(Symbol(
            name=name,
            kind=SymbolKind.CLASS,
            line_start=start_line + 1,
            line_end=end_line + 1,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        ))

    for m in _RE_FUNC_DECL_SIMPLE.finditer(source):
        func_name = m.group(1)
        if func_name in _KEYWORDS:
            continue
            
        start_line = source[:m.start()].count("\n")
        end_line = _find_block_end(lines, start_line)
        body_lines = lines[start_line: end_line + 1]
        body = "\n".join(body_lines)
        
        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        calls = _extract_calls(body)
        lc = end_line - start_line + 1
        complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
        
        symbols.append(Symbol(
            name=func_name,
            kind=SymbolKind.FUNCTION,
            line_start=start_line + 1,
            line_end=end_line + 1,
            calls=calls,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        ))

    return symbols


@memoize_by_mtime
def parse_file(file_path: str, project_root: str) -> Optional[FileModel]:
    rel_path = os.path.relpath(file_path, project_root)
    name = os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return FileModel(
            name=name, path=file_path, relative_path=rel_path,
            line_count=0, purpose="⚠️ IO Error",
            language="Rust",
        )

    lines = source.splitlines()
    line_count = len(lines)

    try:
        symbols = _parse_symbols(source, lines)
    except Exception:
        symbols = []

    return FileModel(
        name=name,
        path=file_path,
        relative_path=rel_path,
        line_count=line_count,
        symbols=symbols,
        language="Rust",
        raw_imports=_extract_imports(source),
    )


def analyze_directory(root_path: str) -> Project:
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)
    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        lang_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if Path(f).suffix.lower() in RUST_EXTENSIONS
        ])
        if lang_files:
            dir_files[dirpath] = lang_files

    modules: list[Module] = []
    root_files: list[FileModel] = []
    module_map: dict[str, Module] = {}

    for dirpath in sorted(dir_files.keys()):
        parsed_files = [
            fm for f in dir_files[dirpath]
            if (fm := parse_file(f, root_path)) is not None
        ]
        if dirpath == root_path:
            root_files = parsed_files
        else:
            rel = os.path.relpath(dirpath, root_path)
            module = Module(
                name=os.path.basename(dirpath),
                path=dirpath,
                relative_path=rel,
                files=parsed_files,
            )
            module_map[dirpath] = module

    for dirpath, module in sorted(module_map.items()):
        parent = os.path.dirname(dirpath)
        if parent in module_map:
            module_map[parent].submodules.append(module)
        else:
            modules.append(module)

    project = Project(
        name=project_name,
        path=root_path,
        modules=modules,
        root_files=root_files,
    )
    project.metadata.languages = ["Rust"]
    return project

# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter("rust", analyze_directory, extensions=["rs"])
