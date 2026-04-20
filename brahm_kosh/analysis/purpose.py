"""
Purpose Inference Engine for Brahm-Kosh.

Infers the purpose of each file using heuristics:
  - File name patterns
  - Docstring keywords
  - Symbol name patterns
"""

from __future__ import annotations

import os
from brahm_kosh.models import FileModel, Project


# File name → purpose patterns
FILE_NAME_PATTERNS: list[tuple[list[str], str]] = [
    (["test_", "_test", "tests", "conftest"], "🧪 Testing"),
    (["cli", "command", "console", "__main__"], "🚀 Entry Point"),
    (["main", "app", "run", "server"], "🚀 Entry Point"),
    (["model", "schema", "entity", "orm"], "📦 Data Model"),
    (["util", "helper", "common", "misc"], "🔧 Utility"),
    (["config", "settings", "conf", "env"], "⚙️ Configuration"),
    (["api", "route", "endpoint", "view", "handler"], "🌐 API / Routes"),
    (["middleware", "plugin", "hook"], "🔌 Middleware"),
    (["adapter", "connector", "client", "driver"], "🔗 Adapter"),
    (["service", "manager", "controller"], "🎛️ Service / Logic"),
    (["error", "exception"], "⚠️ Error Handling"),
    (["log", "logging", "logger"], "📋 Logging"),
    (["auth", "permission", "security"], "🔐 Security"),
    (["db", "database", "migration", "repository"], "🗄️ Database"),
    (["cache", "memo"], "💾 Caching"),
    (["setup", "install", "build"], "📦 Build / Setup"),
    (["__init__"], "📁 Package Init"),
]

# Docstring / symbol keywords → purpose
KEYWORD_PATTERNS: list[tuple[list[str], str]] = [
    (["test", "assert", "mock", "fixture"], "🧪 Testing"),
    (["parse", "tokenize", "lexer", "ast"], "🧠 Parsing"),
    (["analyze", "score", "compute", "calculate"], "📊 Analysis"),
    (["render", "display", "format", "print", "output"], "🖥️ Output / Rendering"),
    (["read", "write", "load", "save", "serialize"], "💾 I/O"),
    (["validate", "check", "verify"], "✅ Validation"),
    (["transform", "convert", "map", "reduce"], "🔄 Transformation"),
]


def _match_patterns(text: str, patterns: list[tuple[list[str], str]]) -> str | None:
    """Match text against a list of keyword patterns."""
    text_lower = text.lower()
    for keywords, purpose in patterns:
        for keyword in keywords:
            if keyword in text_lower:
                return purpose
    return None


def infer_file_purpose(file_model: FileModel) -> str:
    """
    Infer the purpose of a file based on its name, docstrings, and symbols.
    """
    # 1. Try file name first (strongest signal)
    basename = os.path.splitext(file_model.name)[0]
    purpose = _match_patterns(basename, FILE_NAME_PATTERNS)
    if purpose:
        return purpose

    # 2. Try docstrings
    for sym in file_model.symbols:
        if sym.docstring:
            purpose = _match_patterns(sym.docstring, KEYWORD_PATTERNS)
            if purpose:
                return purpose

    # 3. Try symbol names collectively
    all_names = " ".join(s.name for s in file_model.symbols)
    purpose = _match_patterns(all_names, KEYWORD_PATTERNS)
    if purpose:
        return purpose

    # 4. Fallback
    if file_model.symbols:
        return "📄 Source"
    elif file_model.line_count == 0:
        return "📁 Empty"
    else:
        return "📄 Source"


def infer_purposes(project: Project) -> None:
    """
    Infer purpose for every file in the project (mutates in place).
    """
    for file_model in project.all_files():
        file_model.purpose = infer_file_purpose(file_model)
