"""
Brahm-Kosh Engine — The Orchestrator.

Ties together parsing, analysis, and output.
Supports multi-language auto-discovery: one function call, any repo.

Usage:
    project, hotspots = analyze(path)           # auto-detect all languages
    project, hotspots = analyze(path, lang="python")  # target specific language
"""

from __future__ import annotations

import importlib

from brahm_kosh.adapters.registry import detect_languages, get_adapter, list_adapters
from brahm_kosh.analysis.complexity import score_project
from brahm_kosh.analysis.hotspots import Hotspot, find_hotspots
from brahm_kosh.analysis.purpose import infer_purposes
from brahm_kosh.models import FileModel, Metadata, Module, Project

# ---------------------------------------------------------------------------
# Adapter auto-loading
# ---------------------------------------------------------------------------

# All built-in adapter modules. Each module self-registers on import.
_BUILTIN_ADAPTERS = [
    "brahm_kosh.adapters.python_adapter",
    "brahm_kosh.adapters.javascript_adapter",
    "brahm_kosh.adapters.c_adapter",
]


def _load_adapters() -> None:
    """Import all adapter modules so they self-register into the registry."""
    for module_path in _BUILTIN_ADAPTERS:
        try:
            importlib.import_module(module_path)
        except ImportError:
            pass  # Adapter not yet implemented — skip silently


_load_adapters()


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze(
    path: str,
    top_n: int = 10,
    lang: str | None = None,
) -> tuple[Project, list[Hotspot]]:
    """
    Full analysis pipeline.

    Automatically detects languages present in the repo and runs all
    applicable adapters. Results are merged into a single Project model.

    Steps for each detected language:
      1. Parse files → universal code model
      2. Score structural complexity
      3. Rank hotspots
      4. Infer file purposes
      5. Compute metadata

    Args:
        path: Root directory to analyze.
        top_n: Number of hotspots to return.
        lang: If provided, analyze only this language (e.g. 'python', 'javascript', 'c').
              If None, auto-detect all languages present.

    Returns:
        (Project, hotspots) — enriched unified project model and ranked hotspots.
    """
    import os
    root_path = os.path.abspath(path)

    if lang:
        # Explicit language — single adapter
        adapters_to_run = [lang.lower()]
    else:
        # Auto-discover which languages are present
        adapters_to_run = detect_languages(root_path)
        if not adapters_to_run:
            # Fallback — nothing registered matched; default to python
            adapters_to_run = ["python"]

    # Run each adapter and collect sub-projects
    sub_projects: list[Project] = []
    languages_found: list[str] = []

    for adapter_name in adapters_to_run:
        try:
            adapter = get_adapter(adapter_name)
        except ValueError:
            continue  # Adapter not registered (module not yet implemented)

        sub_project = adapter(root_path)

        # Score + purpose
        score_project(sub_project)
        infer_purposes(sub_project)

        sub_projects.append(sub_project)
        languages_found.append(adapter_name.capitalize())

    if not sub_projects:
        # Last resort — empty project
        return Project(name=os.path.basename(root_path), path=root_path), []

    if len(sub_projects) == 1:
        # Single language — no merging needed
        merged = sub_projects[0]
        merged.metadata.languages = languages_found
    else:
        # Multi-language — merge into one Project
        merged = _merge_projects(sub_projects, root_path, languages_found)

    # Compute final metadata
    merged.compute_metadata()
    if languages_found:
        merged.metadata.languages = languages_found

    # Rank hotspots across the merged project
    hotspots = find_hotspots(merged, top_n=top_n)

    return merged, hotspots


def _merge_projects(sub_projects: list[Project], root_path: str, languages: list[str]) -> Project:
    """
    Merge multiple single-language Project models into one unified Project.

    Modules and root files from each sub-project are combined under a single
    Project root. Language label is carried via the Metadata.
    """
    import os
    merged = Project(
        name=os.path.basename(root_path),
        path=root_path,
    )
    for sp in sub_projects:
        merged.modules.extend(sp.modules)
        merged.root_files.extend(sp.root_files)
    return merged
