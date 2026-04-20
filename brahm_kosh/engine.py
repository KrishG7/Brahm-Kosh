"""
Brahm-Kosh Engine — The Orchestrator.

Ties together parsing, analysis, and output.
One function call: repo path → enriched Project model.
"""

from __future__ import annotations

import brahm_kosh.adapters.python_adapter  # triggers registration
from brahm_kosh.adapters.registry import get_adapter
from brahm_kosh.analysis.complexity import score_project
from brahm_kosh.analysis.hotspots import Hotspot, find_hotspots
from brahm_kosh.analysis.purpose import infer_purposes
from brahm_kosh.models import Project


def analyze(path: str, top_n: int = 10) -> tuple[Project, list[Hotspot]]:
    """
    Full analysis pipeline:
      1. Parse all Python files into the universal code model
      2. Score structural complexity
      3. Rank hotspots
      4. Infer file purposes
      5. Compute metadata

    Returns the enriched Project and the top hotspots.
    """
    # Step 1: Parse
    adapter = get_adapter("python")
    project = adapter(path)

    # Step 2: Score complexity
    score_project(project)

    # Step 3: Find hotspots
    hotspots = find_hotspots(project, top_n=top_n)

    # Step 4: Infer purpose
    infer_purposes(project)

    # Step 5: Compute metadata
    project.compute_metadata()

    return project, hotspots
