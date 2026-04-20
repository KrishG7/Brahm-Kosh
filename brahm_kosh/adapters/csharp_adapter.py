"""
C# Adapter for Brahm-Kosh.

Parses .cs files using pure-Python regex analysis.
Extracts:
  - Class/Struct/Interface declarations
  - Method declarations
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


SKIP_DIRS = {
    ".git", "bin", "obj", ".vs", "Properties", "packages",
}

CSHARP_EXTENSIONS = {".cs"}


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


# Regex patterns
_RE_CLASS_DECL = re.compile(
    r"^[ \t]*(?:(?:public|protected|internal|private|abstract|sealed|static|partial)\s+)*"
    r"(class|struct|interface|record)\s+(\w+)",
    re.MULTILINE,
)

_RE_METHOD_DECL = re.compile(
    r"^[ \t]+(?:(?:public|protected|internal|private|virtual|sealed|override|abstract|static|extern|unsafe|async)\s+)*"
    r"(?:[\w<>,\[\]?]+\s+)+" # Return type
    r"(\w+)\s*\([^)]*\)"
    r"(?:\s*where\s+.*)?"
    r"\s*\{",
    re.MULTILINE,
)

_RE_BRANCH = re.compile(
    r"\b(if|else\s+if|for|foreach|while|switch|case\b|catch|finally|try)\b",
    re.MULTILINE,
)

_RE_CALL = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

_KEYWORDS = {
    "if", "for", "foreach", "while", "switch", "return", "catch", "try", 
    "class", "interface", "new", "throw", "void", "base", "this", "case",
    "typeof", "nameof", "sizeof"
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

    for m in _RE_CLASS_DECL.finditer(source):
        class_type = m.group(1)
        class_name = m.group(2)
        
        class_line = source[:m.start()].count("\n")
        class_end = _find_block_end(lines, class_line)
        class_body_lines = lines[class_line: class_end + 1]
        class_body = "\n".join(class_body_lines)

        methods: list[Symbol] = []
        for mm in _RE_METHOD_DECL.finditer(class_body):
            method_name = mm.group(1)
            if method_name in _KEYWORDS:
                continue
            local_line = class_body[:mm.start()].count("\n")
            abs_line = class_line + local_line
            method_end = _find_block_end(lines, abs_line)
            mbody_lines = lines[abs_line: method_end + 1]
            mbody = "\n".join(mbody_lines)

            branches = _count_branches(mbody)
            nesting = _count_nesting_depth(mbody_lines)
            calls = _extract_calls(mbody)
            lc = method_end - abs_line + 1
            complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
            methods.append(Symbol(
                name=method_name,
                kind=SymbolKind.METHOD,
                line_start=abs_line + 1,
                line_end=method_end + 1,
                calls=calls,
                nesting_depth=nd,
                branch_count=bc,
                complexity=complexity,
            ))

        lc = class_end - class_line + 1
        branches = _count_branches(class_body)
        nesting = _count_nesting_depth(class_body_lines)
        complexity, nd, bc = _score_symbol(lc, nesting, branches, 0)

        symbols.append(Symbol(
            name=class_name,
            kind=SymbolKind.CLASS,
            line_start=class_line + 1,
            line_end=class_end + 1,
            children=methods,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        ))

    return symbols


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
            language="C#",
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
        language="C#",
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
            if Path(f).suffix.lower() in CSHARP_EXTENSIONS
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
    project.metadata.languages = ["C#"]
    return project

# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter("csharp", analyze_directory, extensions=["cs"])
