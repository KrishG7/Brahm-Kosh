"""
Adapter Registry bounds the various language parser plugins.

It provides a single interface for the engine to fetch the correct adapter
based on configuration or auto-discovery.
"""

from typing import Callable
from brahm_kosh.models import Project

# An adapter is a function that takes a directory path and returns a populated Project
AdapterFunc = Callable[[str], Project]

_ADAPTERS: dict[str, AdapterFunc] = {}

def register_adapter(name: str, func: AdapterFunc) -> None:
    """Register a new language adapter."""
    _ADAPTERS[name.lower()] = func

def get_adapter(name: str = "python") -> AdapterFunc:
    """Get an adapter by name. Defaults to python."""
    name = name.lower()
    if name not in _ADAPTERS:
        # For now, it defaults to Python and raises if missing, 
        # but in the future this could auto-discover based on project files.
        raise ValueError(f"No adapter registered for language: {name}")
    return _ADAPTERS[name]
