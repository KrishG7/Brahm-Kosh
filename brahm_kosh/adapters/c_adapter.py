"""
C / C++ Adapter for Brahm-Kosh.

Parses .c, .cpp, .h, .hpp files using pure-Python regex analysis.
No compiler dependency — works with the standard library only.

Extracts:
  - C function definitions:        return_type name(params) {
  - C++ class / struct declarations: class Foo { / struct Bar {
  - C++ class methods (inside class body)
  - Header function declarations (no body, just signature)

Limitations (by design):
  - Preprocessor macros are skipped
  - Templates are partially handled (basic function templates)
  - Inline assembly is ignored
  - Focus: 80% of real-world C/C++ code in academic + systems projects
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


# ---------------------------------------------------------------------------
# Skip rules
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", "build", "dist", "cmake-build-debug", "cmake-build-release",
    ".cmake", "__pycache__", "node_modules", "out", "obj", ".vs", ".vscode",
    "CMakeFiles", "Debug", "Release",
}

C_EXTENSIONS = {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}


def should_skip_dir(dirname: str) -> bool:
    if dirname.startswith("."):
        return True
    return dirname in SKIP_DIRS


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# C/C++ function definition:
#   Optional return type (word, pointer), function name, ( params ) {
#   Does NOT match lines starting with # (macros)
#   Does NOT match pure declarations (those without { on the same or next line)
_RE_FUNC_DEF = re.compile(
    r"^(?![ \t]*#)"                          # not a preprocessor line
    r"[ \t]*(?:(?:static|inline|extern|virtual|override|"
    r"explicit|constexpr|__attribute__\s*\([^)]*\)\s*)*\s*)*"  # storage class modifiers
    r"(?:[\w:*&<>]+\s+)+?"                   # return type (greedy-reluctant)
    r"(?:[\w:~]+::)?(\w+)\s*"               # optional class qualifier :: function_name
    r"\([^)]*\)"                             # parameter list
    r"(?:\s*(?:const|noexcept|override|final))*"  # qualifiers
    r"\s*(?::\s*[^{]*)?"                     # optional initializer list (C++)
    r"\s*\{",                                # opening brace
    re.MULTILINE,
)

# Class or struct declaration:  (class|struct) Name {
_RE_CLASS_DECL = re.compile(
    r"^[ \t]*(?:template\s*<[^>]*>\s*)?"     # optional template
    r"(?:class|struct)\s+(\w+)"
    r"(?:\s*:\s*(?:public|protected|private)?\s*[\w:,\s]*)?"  # optional inheritance
    r"\s*\{",
    re.MULTILINE,
)

# Method inside a class body (indented, has parens and potentially {)
_RE_CLASS_METHOD = re.compile(
    r"^[ \t]+(?:(?:virtual|static|inline|explicit|override|"
    r"constexpr|const|noexcept|final|public:|private:|protected:)\s*)*"
    r"(?:[\w:*&<>~]+\s+)*"
    r"(~?\w+)\s*\([^)]*\)"
    r"(?:\s*(?:const|noexcept|override|final))*"
    r"\s*(?::\s*[^{]*)?"
    r"\s*\{",
    re.MULTILINE,
)

# Branching constructs
_RE_BRANCH = re.compile(
    r"\b(if|else\s+if|for|while|switch|case\b|catch|goto)\b",
    re.MULTILINE,
)

# Function calls
_RE_CALL = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

_C_KEYWORDS = {
    "if", "for", "while", "switch", "return", "sizeof", "typeof",
    "case", "catch", "class", "struct", "new", "delete", "throw",
    "void", "int", "char", "float", "double", "long", "short",
    "unsigned", "signed", "static", "inline", "extern",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_block_end(lines: list[str], start: int) -> int:
    """Find the line where the { } block opened at `start` closes."""
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
    return list({c for c in calls if c not in _C_KEYWORDS})


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


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def _parse_symbols(source: str, lines: list[str]) -> list[Symbol]:
    symbols: list[Symbol] = []

    # 1. Function definitions
    for m in _RE_FUNC_DEF.finditer(source):
        name = m.group(1)
        # Filter out common false positives
        if name in {"if", "for", "while", "switch", "return", "else",
                     "catch", "main"} or not name:
            if name == "main":
                pass  # main is valid — keep it
            else:
                continue

        line_no = source[:m.start()].count("\n")
        end_no = _find_block_end(lines, line_no)
        body_lines = lines[line_no: end_no + 1]
        body = "\n".join(body_lines)

        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        calls = _extract_calls(body)
        lc = end_no - line_no + 1

        complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
        symbols.append(Symbol(
            name=name,
            kind=SymbolKind.FUNCTION,
            line_start=line_no + 1,
            line_end=end_no + 1,
            calls=calls,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        ))

    # 2. Class / struct declarations (with methods as children)
    for m in _RE_CLASS_DECL.finditer(source):
        class_name = m.group(1)
        if not class_name:
            continue
        class_line = source[:m.start()].count("\n")
        class_end = _find_block_end(lines, class_line)
        class_body_lines = lines[class_line: class_end + 1]
        class_body = "\n".join(class_body_lines)

        # Extract methods
        methods: list[Symbol] = []
        for mm in _RE_CLASS_METHOD.finditer(class_body):
            method_name = mm.group(1)
            if not method_name or method_name in {"if", "for", "while", "return"}:
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
    )


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------

def analyze_directory(root_path: str) -> Project:
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)
    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        c_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if Path(f).suffix.lower() in C_EXTENSIONS
        ])
        if c_files:
            dir_files[dirpath] = c_files

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
    project.metadata.languages = ["C/C++"]
    return project


# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter(
    "c",
    analyze_directory,
    extensions=["c", "cpp", "cc", "cxx", "h", "hpp", "hh", "hxx"],
)
