"""
SQL Adapter for Brahm-Kosh.

Parses .sql files using pure-Python regex analysis.
Extracts:
  - CREATE TABLE/PROCEDURE/FUNCTION statements
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from brahm_kosh.parse_cache import memoize_by_mtime
from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


SKIP_DIRS = {
    ".git",
}

SQL_EXTENSIONS = {".sql"}


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


# Regex patterns
_RE_DDL_DECL = re.compile(
    r"^[ \t]*CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|PROCEDURE|FUNCTION|VIEW|TRIGGER)\s+([`\"\[\]\w.]+)",
    re.MULTILINE | re.IGNORECASE,
)

_RE_BRANCH = re.compile(
    r"\b(IF|ELSEIF|ELSIF|CASE|WHEN|WHILE|LOOP|FOR)\b",
    re.MULTILINE | re.IGNORECASE,
)

_RE_CALL = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

_KEYWORDS = {
    "IF", "ELSE", "CASE", "WHEN", "THEN", "END", "SELECT", "INSERT", "UPDATE", "DELETE",
    "FROM", "WHERE", "AND", "OR", "IN", "NOT", "IS", "NULL", "AS", "CREATE", "ALTER", "DROP",
    "TABLE", "VIEW", "FUNCTION", "PROCEDURE", "TRIGGER", "INDEX", "PRIMARY", "FOREIGN", "KEY",
    "JOIN", "INNER", "OUTER", "LEFT", "RIGHT", "ON", "GROUP", "BY", "ORDER", "HAVING", "LIMIT",
    "MAX", "MIN", "SUM", "AVG", "COUNT", "COALESCE", "CAST", "CONVERT"
}


def _find_block_end(lines: list[str], start: int) -> int:
    # SQL can end blocks with standard ';' or END blocks
    depth = 0
    for i in range(start, len(lines)):
        upper_line = lines[i].upper()
        
        # Track BEGIN/END depth approximately
        depth += len(re.findall(r"\bBEGIN\b", upper_line))
        depth -= len(re.findall(r"\bEND\b", upper_line))
        
        # If we hit a semicolon and we aren't in a BEGIN/END block, we assume it's done
        if depth <= 0 and ";" in upper_line:
            return i
            
    return len(lines) - 1


def _count_nesting_depth(lines: list[str]) -> int:
    depth = 0
    max_depth = 0
    for line in lines:
        upper_line = line.upper()
        depth += len(re.findall(r"\bBEGIN\b", upper_line))
        depth -= len(re.findall(r"\bEND\b", upper_line))
        depth -= len(re.findall(r"\bCOMMIT\b", upper_line))
        depth = max(depth, 0)
        max_depth = max(max_depth, depth)
    return max_depth


def _count_branches(source: str) -> int:
    return len(_RE_BRANCH.findall(source))


def _extract_calls(source: str) -> list[str]:
    calls = _RE_CALL.findall(source)
    return list({c for c in calls if c.upper() not in _KEYWORDS})


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

    for m in _RE_DDL_DECL.finditer(source):
        stmt_type = m.group(1).upper()
        name = m.group(2).replace("`", "").replace("[", "").replace("]", "").replace('"', "")
            
        start_line = source[:m.start()].count("\n")
        end_line = _find_block_end(lines, start_line)
        body_lines = lines[start_line: end_line + 1]
        body = "\n".join(body_lines)

        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        calls = _extract_calls(body)
        lc = end_line - start_line + 1
        complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
        
        kind = SymbolKind.CLASS if stmt_type in ("TABLE", "VIEW") else SymbolKind.FUNCTION

        symbols.append(Symbol(
            name=f"{name} ({stmt_type.lower()})",
            kind=kind,
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
            language="SQL",
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
        language="SQL",
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
            if Path(f).suffix.lower() in SQL_EXTENSIONS
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
    project.metadata.languages = ["SQL"]
    return project

# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter("sql", analyze_directory, extensions=["sql"])
