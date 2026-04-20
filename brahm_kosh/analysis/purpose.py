"""
Purpose Inference Engine for Brahm-Kosh.

Infers the purpose of each file using a layered heuristic system:
  1. File name pattern matching (strongest signal)
  2. Docstring content keywords
  3. Symbol name collective analysis
  4. Symbol kind dominance (e.g. all classes → data model)
  5. File size heuristics (tiny files, large files)
"""

from __future__ import annotations

import os
from brahm_kosh.models import FileModel, Project, SymbolKind


# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

# File name → purpose patterns (first match wins)
FILE_NAME_PATTERNS: list[tuple[list[str], str]] = [
    # Testing
    (["test_", "_test", "tests/", "conftest", "spec_", "_spec", ".spec"], "🧪 Testing"),
    # Entry points
    (["__main__", "cli", "command", "console"], "🚀 Entry Point"),
    (["main", "app", "run", "server", "wsgi", "asgi", "index"], "🚀 Entry Point"),
    # Data models & schemas
    (["model", "schema", "entity", "orm", "dto", "dataclass"], "📦 Data Model"),
    # Config & settings
    (["config", "settings", "conf", "env", "constants", "defaults"], "⚙️ Configuration"),
    # APIs & routing
    (["api", "route", "router", "endpoint", "view", "handler", "urls"], "🌐 API / Routes"),
    # Frontend layout & pages
    (["index", "layout", "template", "page", "screen", "component"], "🖼️ Layout / View"),
    # Styling
    (["style", "styles", "theme", "global", "tailwind", "colors"], "🎨 Styling"),
    # Middleware & plugins
    (["middleware", "plugin", "hook", "signal", "event"], "🔌 Middleware"),
    # Adapters & connectors
    (["adapter", "connector", "client", "driver", "gateway", "bridge"], "🔗 Adapter"),
    # Services & controllers
    (["service", "manager", "controller", "repository", "store"], "🎛️ Service / Logic"),
    # Error handling
    (["error", "exception", "fault", "trap"], "⚠️ Error Handling"),
    # Logging
    (["log", "logging", "logger", "audit"], "📋 Logging"),
    # Security
    (["auth", "permission", "security", "token", "jwt", "oauth"], "🔐 Security"),
    # Database
    (["db", "database", "migration", "seed", "fixture", "sql"], "🗄️ Database"),
    # Caching
    (["cache", "memo", "redis", "memcache"], "💾 Caching"),
    # Build & setup
    (["setup", "install", "build", "deploy", "docker", "makefile"], "📦 Build / Setup"),
    # Utilities (generic — intentionally placed late to avoid false positives)
    (["util", "utils", "helper", "helpers", "common", "shared", "misc", "tools"], "🔧 Utility"),
    # Package init — most generic
    (["__init__"], "📁 Package Init"),
    # Registry / registry pattern
    (["registry", "register", "factory", "provider"], "🏭 Registry / Factory"),
]

# Docstring / symbol keyword → purpose (searched in order)
KEYWORD_PATTERNS: list[tuple[list[str], str]] = [
    (["test", "assert", "mock", "fixture", "pytest", "unittest"], "🧪 Testing"),
    (["parse", "tokenize", "lexer", "ast", "grammar", "token"], "🧠 Parsing"),
    (["analyze", "score", "compute", "calculate", "rank", "hotspot", "complexity"], "📊 Analysis"),
    (["render", "display", "format", "print", "output", "rich", "console", "table", "tree"], "🖥️ Output / Rendering"),
    (["read", "write", "load", "save", "serialize", "deserialize", "dump", "open"], "💾 I/O"),
    (["validate", "check", "verify", "assert", "constraint"], "✅ Validation"),
    (["transform", "convert", "map", "reduce", "filter", "pipeline"], "🔄 Transformation"),
    (["register", "factory", "create", "build", "inject"], "🏭 Registry / Factory"),
    (["route", "dispatch", "handle", "middleware"], "🌐 API / Routes"),
    (["config", "setting", "option", "parameter", "preference"], "⚙️ Configuration"),
    (["css", "style", "color", "font", "margin", "padding", "flex", "grid"], "🎨 Styling"),
    (["html", "div", "span", "component", "render", "jsx", "tsx"], "🖼️ Layout / View"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_patterns(text: str, patterns: list[tuple[list[str], str]]) -> str | None:
    """Return the purpose label for the first pattern that matches text."""
    text_lower = text.lower()
    for keywords, purpose in patterns:
        for keyword in keywords:
            if keyword in text_lower:
                return purpose
    return None


def _dominant_symbol_kind(file_model: FileModel) -> SymbolKind | None:
    """Return the dominant symbol kind if ≥75% of top-level symbols share a kind."""
    if not file_model.symbols:
        return None
    from collections import Counter
    kind_counts = Counter(s.kind for s in file_model.symbols)
    total = len(file_model.symbols)
    dominant, count = kind_counts.most_common(1)[0]
    if count / total >= 0.75:
        return dominant
    return None


# ---------------------------------------------------------------------------
# Main inference
# ---------------------------------------------------------------------------

def infer_file_purpose(file_model: FileModel) -> str:
    """
    Infer the purpose of a file based on layered heuristics.

    Priority:
      1. File name pattern (strongest signal)
      2. Docstring keywords (top-level symbols)
      3. Collective symbol name keywords
      4. Symbol kind dominance
      5. Size-based fallback
    """
    # 1. File name (no extension)
    basename = os.path.splitext(file_model.name)[0]
    # Also check parent directory name for context (e.g. tests/ dir)
    parent = os.path.basename(os.path.dirname(file_model.relative_path))
    combined_name = f"{parent}/{basename}"

    purpose = _match_patterns(combined_name, FILE_NAME_PATTERNS)
    if purpose:
        return purpose

    # 2. Docstrings of top-level symbols (module-level docstrings are in sym.docstring)
    for sym in file_model.symbols:
        if sym.docstring:
            purpose = _match_patterns(sym.docstring, KEYWORD_PATTERNS)
            if purpose:
                return purpose
            # Also check child docstrings (methods)
            for child in sym.children:
                if child.docstring:
                    purpose = _match_patterns(child.docstring, KEYWORD_PATTERNS)
                    if purpose:
                        return purpose

    # 3. Collective symbol names
    all_names = " ".join(s.name for s in file_model.symbols)
    if all_names:
        purpose = _match_patterns(all_names, KEYWORD_PATTERNS)
        if purpose:
            return purpose

    # 4. Symbol kind dominance
    dominant = _dominant_symbol_kind(file_model)
    if dominant == SymbolKind.CLASS:
        return "📦 Data Model"
    if dominant == SymbolKind.CSS_RULE:
        return "🎨 Styling"
    if dominant == SymbolKind.HTML_NODE:
        return "🖼️ Layout / View"
    if dominant == SymbolKind.FUNCTION:
        # Many functions, no other hints → likely utility or analysis
        if file_model.symbol_count > 8:
            return "🔧 Utility"

    # 5. Fallback by size
    if file_model.line_count == 0:
        return "📁 Empty"
    if file_model.line_count < 10:
        return "📄 Stub / Init"
    return "📄 Source"


def infer_purposes(project: Project) -> None:
    """
    Infer purpose for every file in the project (mutates in place).
    """
    for file_model in project.all_files():
        file_model.purpose = infer_file_purpose(file_model)
