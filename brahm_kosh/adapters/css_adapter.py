"""
CSS Adapter for Brahm-Kosh.

Parses .css files.
Extracts CSS selectors as Symbols.
Complexity is driven by the length of the selector block and
the number of rules (declarations) inside it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "coverage", ".cache",
    "venv", ".venv", ".tox",
}

CSS_EXTENSIONS = {".css"}


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


def _score_css_symbol(line_count: int, rules: int) -> float:
    from brahm_kosh.analysis.complexity import (
        MAX_BRANCHES, MAX_LINES,
        WEIGHT_BRANCHES, WEIGHT_LINES,
        _clamp,
    )
    # Re-map branches to rules
    raw = (
        WEIGHT_LINES * min(line_count / MAX_LINES, 1.0) * 100
        + WEIGHT_BRANCHES * min(rules / MAX_BRANCHES, 1.0) * 100
        # Ignore nesting/calls for CSS symbols (score base)
    )
    return _clamp(raw)


def _parse_symbols(source: str, lines: list[str]) -> list[Symbol]:
    symbols: list[Symbol] = []
    
    # Simple block parser to handle { }
    depth = 0
    current_selector = ""
    start_line = -1
    
    in_comment = False
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Extremely basic comment removal for the line
        if "/*" in line_clean and "*/" in line_clean:
            # Inline comment
            line_clean = line_clean.split("/*")[0] + line_clean.split("*/")[1]
            
        if "/*" in line_clean:
            in_comment = True
            line_clean = line_clean.split("/*")[0]
            
        if "*/" in line_clean:
            in_comment = False
            line_clean = line_clean.split("*/")[1]
            
        if in_comment:
            continue
            
        # Accumulate selector logic
        if "{" in line_clean:
            # Found opening of a block
            parts = line_clean.split("{")
            # The selector might span multiple lines, so we append the part before {
            if parts[0].strip():
                current_selector += " " + parts[0].strip()
                
            if depth == 0:
                start_line = i + 1
                
            depth += line_clean.count("{")
                
        elif "}" in line_clean:
            depth -= line_clean.count("}")
            if depth == 0 and start_line != -1:
                # We closed a block
                sel = current_selector.strip()
                # Clean up multiple spaces and newlines
                sel = " ".join(sel.split())
                
                if sel and not sel.startswith("@"): # ignore @font-face etc that don't have standard rules, or keep them? keep them.
                    end_line = i + 1
                    block_lines = lines[start_line-1:end_line]
                    block_text = "\n".join(block_lines)
                    
                    rules_count = block_text.count(";")
                    lc = end_line - start_line + 1
                    
                    sym = Symbol(
                        name=sel[:50] + "..." if len(sel) > 50 else sel,
                        kind=SymbolKind.CSS_RULE,
                        line_start=start_line,
                        line_end=end_line,
                        branch_count=rules_count, # Use rules count as branch metric
                        complexity=_score_css_symbol(lc, rules_count)
                    )
                    symbols.append(sym)
                    
                current_selector = ""
                start_line = -1
        else:
            if depth == 0:
                # Outside a block, accumulating selector lines
                current_selector += " " + line_clean
                
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
            line_count=0, symbols=[], purpose="⚠️ IO Error",
            language="CSS",
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
        language="CSS",
    )


def analyze_directory(root_path: str) -> Project:
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)

    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        css_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if Path(f).suffix.lower() in CSS_EXTENSIONS
        ])
        if css_files:
            dir_files[dirpath] = css_files

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
    project.metadata.languages = ["CSS"]
    return project


# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter(
    "css",
    analyze_directory,
    extensions=["css"],
)
