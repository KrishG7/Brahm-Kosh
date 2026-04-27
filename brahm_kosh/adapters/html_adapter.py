"""
HTML Adapter for Brahm-Kosh.

Parses .html and .htm files.
Unlike imperative languages, HTML complexity is primarily architectural:
  - Deep nesting depth ("div soup")
  - Extremely large inline structure
  - Meaningful structural nodes (IDs, <script>, <style>, <section>, etc.)

Uses Python's built-in `html.parser` to build the hierarchy without dependencies.
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from brahm_kosh.parse_cache import memoize_by_mtime
from brahm_kosh.models import FileModel, Module, Project, Symbol, SymbolKind


SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "coverage", ".cache",
    "venv", ".venv", ".tox",
}

HTML_EXTENSIONS = {".html", ".htm"}


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


# Tags that do not have end tags
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr", "!doctype"
}

# Tags that we consider "structural" and worthy of being a Symbol even without an ID
STRUCTURAL_TAGS = {
    "script", "style", "main", "header", "footer", "nav",
    "article", "section", "aside", "form", "dialog"
}


class BrahmHTMLParser(HTMLParser):
    def __init__(self, source_lines: list[str]):
        super().__init__()
        self.source_lines = source_lines
        self.current_depth = 0
        self.max_depth = 0

        self.root_symbols: list[Symbol] = []
        # Stack stores tuples of (tag_name, Symbol)
        self.stack: list[tuple[str, Symbol]] = []
        # Local asset references: <script src>, <link href> — skip protocol URLs.
        self.imports: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attr_dict = dict(attrs)

        # Asset linkage — record before early-returning for void tags
        src = None
        if tag == "script":
            src = attr_dict.get("src")
        elif tag == "link":
            src = attr_dict.get("href")
        elif tag in ("img", "iframe", "audio", "video", "source"):
            src = attr_dict.get("src")
        if src and not src.startswith(("http://", "https://", "//", "data:", "mailto:", "#")):
            self.imports.append(src)

        if tag in VOID_TAGS:
            return

        self.current_depth += 1
        self.max_depth = max(self.max_depth, self.current_depth)

        tag_id = attr_dict.get("id")
        
        # Decide if this tag is a Symbol
        is_symbol = False
        symbol_name = ""
        
        if tag_id:
            is_symbol = True
            symbol_name = f"#{tag_id} ({tag})"
        elif tag in STRUCTURAL_TAGS:
            is_symbol = True
            symbol_name = f"<{tag}>"
            
        if is_symbol:
            line_no = self.getpos()[0]  # 1-indexed
            sym = Symbol(
                name=symbol_name,
                kind=SymbolKind.HTML_NODE,
                line_start=line_no,
                line_end=line_no,  # updated on close
                nesting_depth=self.current_depth,
                branch_count=len(attrs),  # Use attribute count as a pseudo-"branch" metric
            )
            
            if self.stack:
                self.stack[-1][1].children.append(sym)
            else:
                self.root_symbols.append(sym)
                
            self.stack.append((tag, sym))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_TAGS:
            return
            
        self.current_depth = max(0, self.current_depth - 1)
        
        # Unwind stack if we are closing a tracked symbol
        # Look backwards to find the matching open tag
        match_idx = -1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                match_idx = i
                break
                
        if match_idx != -1:
            # We found a matching tag. Everything above it was unclosed or implicitly closed.
            line_no = self.getpos()[0]
            for i in range(len(self.stack) - 1, match_idx - 1, -1):
                popped_tag, popped_sym = self.stack.pop()
                popped_sym.line_end = line_no

                # Calculate complexity just before finalizing
                from brahm_kosh.analysis.complexity import (
                    MAX_BRANCHES, MAX_LINES, MAX_NESTING,
                    WEIGHT_BRANCHES, WEIGHT_LINES, WEIGHT_NESTING,
                    _clamp,
                )
                
                # For HTML, we shift weights a bit conceptually, but use the same engine scaling
                # Line count matters, nesting depth matters a LOT.
                lc = popped_sym.line_count
                nd = popped_sym.nesting_depth
                attrs = popped_sym.branch_count 
                
                raw = (
                    WEIGHT_LINES * min(lc / MAX_LINES, 1.0) * 100
                    + WEIGHT_NESTING * min(nd / MAX_NESTING, 1.0) * 100
                    + WEIGHT_BRANCHES * min(attrs / MAX_BRANCHES, 1.0) * 100
                )
                popped_sym.complexity = _clamp(raw)


@memoize_by_mtime
def parse_file(file_path: str, project_root: str) -> Optional[FileModel]:
    """Parse an HTML file into a FileModel."""
    rel_path = os.path.relpath(file_path, project_root)
    name = os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return FileModel(
            name=name, path=file_path, relative_path=rel_path,
            line_count=0, symbols=[], purpose="⚠️ IO Error",
            language="HTML",
        )

    lines = source.splitlines()
    parser = BrahmHTMLParser(lines)
    try:
        parser.feed(source)
        parser.close()
    except Exception:
        pass # Best effort

    # Any unclosed symbols on stack just run to end of file
    for tag, sym in parser.stack:
        sym.line_end = len(lines)
        
    return FileModel(
        name=name,
        path=file_path,
        relative_path=rel_path,
        line_count=len(lines),
        symbols=parser.root_symbols,
        language="HTML",
        raw_imports=list(parser.imports),
    )


def analyze_directory(root_path: str) -> Project:
    root_path = os.path.abspath(root_path)
    project_name = os.path.basename(root_path)

    dir_files: dict[str, list[str]] = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        html_files = sorted([
            os.path.join(dirpath, f)
            for f in filenames
            if Path(f).suffix.lower() in HTML_EXTENSIONS
        ])
        if html_files:
            dir_files[dirpath] = html_files

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
    project.metadata.languages = ["HTML"]
    return project


# Self-register
from brahm_kosh.adapters.registry import register_adapter
register_adapter(
    "html",
    analyze_directory,
    extensions=["html", "htm"],
)
