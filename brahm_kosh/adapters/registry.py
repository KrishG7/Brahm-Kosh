"""
Adapter Registry for Brahm-Kosh.

Provides a pluggable interface for language adapters.
Each adapter registers itself by calling register_adapter() on import.

Language detection maps file extensions to adapter names.
The engine calls list_adapters() to discover what's available,
then auto-routes based on which languages are present in the repo.

Supports .brahmkoshignore files — one glob pattern per line, # for comments.
"""

from __future__ import annotations

import fnmatch
import os
from functools import lru_cache
from typing import Callable

from brahm_kosh.models import Project


# ---------------------------------------------------------------------------
# .brahmkoshignore support
# ---------------------------------------------------------------------------

_BUILTIN_SKIP_DIRS = {
    "node_modules", "__pycache__", "venv", ".venv", "env", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache", ".git", ".hg", ".svn",
    "vendor", "third_party", "site-packages",
}


@lru_cache(maxsize=8)
def load_ignore_patterns(root_path: str) -> list[str]:
    """Load patterns from <root>/.brahmkoshignore. Cached per root."""
    ignore_file = os.path.join(root_path, ".brahmkoshignore")
    patterns: list[str] = []
    try:
        with open(ignore_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    except FileNotFoundError:
        pass
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Return True if rel_path matches any ignore pattern."""
    name = os.path.basename(rel_path)
    for pat in patterns:
        if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False

# An adapter is a function: (directory_path: str) -> Project
AdapterFunc = Callable[[str], Project]

_ADAPTERS: dict[str, AdapterFunc] = {}

# Maps file extension (without dot) → adapter name
EXTENSION_MAP: dict[str, str] = {}


def register_adapter(name: str, func: AdapterFunc, extensions: list[str] | None = None) -> None:
    """
    Register a language adapter.

    Args:
        name: Adapter name (e.g. 'python', 'javascript', 'c')
        func: Callable that takes a directory path and returns a populated Project
        extensions: File extensions this adapter handles (e.g. ['py'] for Python)
    """
    key = name.lower()
    _ADAPTERS[key] = func
    if extensions:
        for ext in extensions:
            EXTENSION_MAP[ext.lower().lstrip(".")] = key


def get_adapter(name: str) -> AdapterFunc:
    """Get a specific adapter by name. Raises ValueError if not registered."""
    key = name.lower()
    if key not in _ADAPTERS:
        available = ", ".join(_ADAPTERS.keys()) or "(none registered)"
        raise ValueError(
            f"No adapter registered for language: '{name}'. "
            f"Available: {available}"
        )
    return _ADAPTERS[key]


def list_adapters() -> dict[str, list[str]]:
    """
    Return a mapping of adapter_name → [extensions] for all registered adapters.

    Used by 'brahm-kosh list-adapters' and the auto-discovery engine.
    """
    result: dict[str, list[str]] = {name: [] for name in _ADAPTERS}
    for ext, adapter_name in EXTENSION_MAP.items():
        if adapter_name in result:
            result[adapter_name].append(f".{ext}")
    return result


def detect_languages(root_path: str) -> list[str]:
    """
    Walk root_path and detect which registered adapter languages are present.

    Respects .brahmkoshignore patterns and the built-in skip directory list.
    Returns a list of adapter names (e.g. ['python', 'javascript']) for
    languages that have at least one matching file in the directory tree.
    """
    found: set[str] = set()
    patterns = load_ignore_patterns(root_path)
    for dirpath, dirnames, filenames in os.walk(root_path):
        rel_dir = os.path.relpath(dirpath, root_path)
        # Skip hidden dirs, builtin skip list, and .brahmkoshignore patterns
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in _BUILTIN_SKIP_DIRS
            and not d.endswith(".egg-info")
            and not is_ignored(os.path.join(rel_dir, d).replace("\\", "/"), patterns)
        ]
        for filename in filenames:
            rel_file = os.path.join(rel_dir, filename).replace("\\", "/")
            if is_ignored(rel_file, patterns):
                continue
            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if ext in EXTENSION_MAP:
                found.add(EXTENSION_MAP[ext])
            if len(found) == len(_ADAPTERS):
                return sorted(found)
    return sorted(found)
