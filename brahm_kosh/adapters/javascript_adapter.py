"""
JavaScript / TypeScript Adapter for Brahm-Kosh.

Parses .js, .ts, .jsx, .tsx files using pure-Python regex analysis.
No Node.js dependency — works with the standard library only.

Extracts:
  - Named function declarations:   function foo() {}
  - Arrow function assignments:    const foo = () => {}
  - Async variants:                async function foo() {}
  - Class declarations:            class Foo {}
  - Class methods:                 foo() {} inside a class
  - TypeScript arrow functions:    const foo = (): ReturnType => {}

Complexity scoring mirrors the Python adapter:
  - Line count, nesting depth (if/for/while/try), branch count, call sites
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


# ---------------------------------------------------------------------------
# Skip rules (same conventions as Python adapter)
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt", ".svelte-kit",
    "coverage", ".cache", ".parcel-cache", "__pycache__", "venv", ".venv",
    ".tox", ".mypy_cache", ".pytest_cache",
}

JS_EXTENSIONS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}


def should_skip_dir(dirname: str) -> bool:
    if dirname.startswith("."):
        return True
    if dirname in SKIP_DIRS:
        return True
    if dirname.endswith(".egg-info"):
        return True
    return False


# ---------------------------------------------------------------------------
# Regex patterns for JavaScript/TypeScript construct detection
# ---------------------------------------------------------------------------

# Named function declaration:  (export) (default) (async) function name(
_RE_FUNCTION_DECL = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*[(<]",
    re.MULTILINE,
)

# Arrow / const assignment:    (export) (const|let|var) name = (async) (...) =>
_RE_ARROW_FUNC = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*[:=][^=].*?(?:async\s+)?\(?[^)]*\)?\s*(?::\s*\S+\s*)?=>",
    re.MULTILINE,
)

# Class declaration:           (export) (default) (abstract) class Name
_RE_CLASS_DECL = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)

# Class method:                methodName( or async methodName( (not constructor or super)
_RE_CLASS_METHOD = re.compile(
    r"^[ \t]+(?:(?:public|private|protected|static|async|override|readonly)\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*\S+\s*)?[{]",
    re.MULTILINE,
)

# Branching constructs for complexity
_RE_BRANCH = re.compile(
    r"\b(if|else\s+if|for|while|switch|catch|finally|case\b)\b",
    re.MULTILINE,
)

# Function/method calls
_RE_CALL = re.compile(r"\b(\w+)\s*\(", re.MULTILINE)

# Nesting: opening braces / brackets that deepen control flow
_RE_OPEN_BRACE = re.compile(r"[{(]")
_RE_CLOSE_BRACE = re.compile(r"[})]")


# ---------------------------------------------------------------------------
# Complexity counting
# ---------------------------------------------------------------------------

def _count_nesting_depth(lines: list[str]) -> int:
    """Estimate maximum nesting depth by tracking brace balance."""
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
    # Exclude common keywords that look like calls
    _KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "class",
                 "return", "typeof", "instanceof", "new", "delete", "void", "throw"}
    calls = _RE_CALL.findall(source)
    return [c for c in calls if c not in _KEYWORDS]


# ---------------------------------------------------------------------------
# Symbol parsing helpers
# ---------------------------------------------------------------------------

def _find_block_end(lines: list[str], start: int) -> int:
    """Find the end line of a {...} block starting from `start`."""
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth < 0:
            depth = 0
        if depth == 0 and i > start:
            return i
    return len(lines) - 1


def _score_symbol(line_count: int, nesting: int, branches: int, calls: int) -> tuple[float, int, int]:
    """Return (raw_complexity_0_100, nesting, branches) — not yet clamped to int."""
    from brahm_kosh.analysis.complexity import (
        MAX_BRANCHES, MAX_CALLS, MAX_LINES, MAX_NESTING,
        WEIGHT_BRANCHES, WEIGHT_CALLS, WEIGHT_LINES, WEIGHT_NESTING,
        _clamp,
    )
    line_score = min(line_count / MAX_LINES, 1.0) * 100
    nesting_score = min(nesting / MAX_NESTING, 1.0) * 100
    branch_score = min(branches / MAX_BRANCHES, 1.0) * 100
    call_score = min(calls / MAX_CALLS, 1.0) * 100
    raw = (
        WEIGHT_LINES * line_score
        + WEIGHT_NESTING * nesting_score
        + WEIGHT_BRANCHES * branch_score
        + WEIGHT_CALLS * call_score
    )
    return _clamp(raw), nesting, branches


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def _parse_symbols_from_source(source: str, lines: list[str]) -> list[Symbol]:
    """Extract symbols (functions, classes+methods) from JS/TS source."""
    symbols: list[Symbol] = []
    source_lines = lines  # alias

    # 1. Named function declarations
    for m in _RE_FUNCTION_DECL.finditer(source):
        line_no = source[:m.start()].count("\n")  # 0-indexed
        end_no = _find_block_end(source_lines, line_no)
        body_lines = source_lines[line_no: end_no + 1]
        body = "\n".join(body_lines)

        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        calls = list(set(_extract_calls(body)))
        lc = end_no - line_no + 1

        complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
        sym = Symbol(
            name=m.group(1),
            kind=SymbolKind.FUNCTION,
            line_start=line_no + 1,
            line_end=end_no + 1,
            calls=calls,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        )
        symbols.append(sym)

    # 2. Arrow function assignments
    for m in _RE_ARROW_FUNC.finditer(source):
        name = m.group(1)
        # Skip if already captured as a function decl
        if any(s.name == name for s in symbols):
            continue
        line_no = source[:m.start()].count("\n")
        end_no = _find_block_end(source_lines, line_no)
        body_lines = source_lines[line_no: end_no + 1]
        body = "\n".join(body_lines)

        branches = _count_branches(body)
        nesting = _count_nesting_depth(body_lines)
        calls = list(set(_extract_calls(body)))
        lc = end_no - line_no + 1

        complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
        sym = Symbol(
            name=name,
            kind=SymbolKind.FUNCTION,
            line_start=line_no + 1,
            line_end=end_no + 1,
            calls=calls,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        )
        symbols.append(sym)

    # 3. Class declarations (with methods as children)
    for m in _RE_CLASS_DECL.finditer(source):
        class_name = m.group(1)
        class_line = source[:m.start()].count("\n")
        class_end = _find_block_end(source_lines, class_line)

        class_body_lines = source_lines[class_line: class_end + 1]
        class_body = "\n".join(class_body_lines)

        # Extract methods inside the class body
        methods: list[Symbol] = []
        for mm in _RE_CLASS_METHOD.finditer(class_body):
            method_name = mm.group(1)
            if method_name in {"constructor", "super", "return", "if", "for", "while"}:
                continue
            method_local_line = class_body[: mm.start()].count("\n")
            method_abs_line = class_line + method_local_line
            method_end = _find_block_end(source_lines, method_abs_line)
            method_body_lines = source_lines[method_abs_line: method_end + 1]
            method_body = "\n".join(method_body_lines)

            branches = _count_branches(method_body)
            nesting = _count_nesting_depth(method_body_lines)
            calls = list(set(_extract_calls(method_body)))
            lc = method_end - method_abs_line + 1

            complexity, nd, bc = _score_symbol(lc, nesting, branches, len(calls))
            methods.append(Symbol(
                name=method_name,
                kind=SymbolKind.METHOD,
                line_start=method_abs_line + 1,
                line_end=method_end + 1,
                calls=calls,
                nesting_depth=nd,
                branch_count=bc,
                complexity=complexity,
            ))

        branches = _count_branches(class_body)
        nesting = _count_nesting_depth(class_body_lines)
        lc = class_end - class_line + 1
        complexity, nd, bc = _score_symbol(lc, nesting, branches, 0)

        class_sym = Symbol(
            name=class_name,
            kind=SymbolKind.CLASS,
            line_start=class_line + 1,
            line_end=class_end + 1,
            children=methods,
            nesting_depth=nd,
            branch_count=bc,
            complexity=complexity,
        )
        symbols.append(class_sym)

    return symbols


def parse_file(file_path: str, project_root: str) -> Optional[FileModel]:
    """Parse a single JS/TS file into a FileModel."""
    rel_path = os.path.relpath(file_path, project_root)
    name = os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return FileModel(
            name=name, path=file_path, relative_path=rel_path,
            line_count=0, symbols=[], purpose="⚠️ IO Error",
        )

    lines = source.splitlines()
    line_count = len(lines)

    try:
        symbols = _parse_symbols_from_source(source, lines)
    except Exception:
        # Parsing failed — return file with no symbols
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
    """
    Walk a directory tree and build the full Project model for JS/TS files.
    """
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)

    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        js_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if Path(f).suffix.lower() in JS_EXTENSIONS
        ])
        if js_files:
            dir_files[dirpath] = js_files

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
    project.metadata.languages = ["JavaScript/TypeScript"]
    return project


# Self-register with all supported extensions
from brahm_kosh.adapters.registry import register_adapter
register_adapter(
    "javascript",
    analyze_directory,
    extensions=["js", "ts", "jsx", "tsx", "mjs", "cjs"],
)
