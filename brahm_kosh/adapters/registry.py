"""
Adapter Registry for Brahm-Kosh.

Provides a pluggable interface for language adapters.
Each adapter registers itself by calling register_adapter() on import.

Language detection maps file extensions to adapter names.
The engine calls list_adapters() to discover what's available,
then auto-routes based on which languages are present in the repo.
"""

from __future__ import annotations

import os
from typing import Callable

from brahm_kosh.models import Project

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

    Returns a list of adapter names (e.g. ['python', 'javascript']) for
    languages that have at least one matching file in the directory tree.
    """
    found: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip hidden dirs and common non-source dirs
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", "venv", ".venv", "env",
                          "dist", "build", ".tox", ".mypy_cache", ".pytest_cache"}
            and not d.endswith(".egg-info")
        ]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if ext in EXTENSION_MAP:
                found.add(EXTENSION_MAP[ext])
            if len(found) == len(_ADAPTERS):
                # All registered languages found — short-circuit
                return sorted(found)
    return sorted(found)
