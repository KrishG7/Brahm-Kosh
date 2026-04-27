"""
Smart Architect Analyzer for Brahm-Kosh.

Scans the dependency graph and the per-file domain set for structural
anti-patterns:
  - Monolithic files (too many incoming dependents)
  - Circular dependencies (A imports B imports A)
  - Dead files (zero edges)
  - Cross-cutting concerns (one file touches many domains — DB + UI + ...)
  - Split candidates (one file contains disconnected groups of symbols)
"""

from typing import Any, Dict, List
from brahm_kosh.models import Project, FileModel
from brahm_kosh.analysis.domains import cross_cutting_files
from brahm_kosh.analysis.refactor import project_split_candidates


def analyze_structure(project: Project) -> Dict[str, Any]:
    files: List[FileModel] = project.all_files()

    monolithic_files: list[dict] = []
    dead_files: list[dict] = []
    circular_deps: list[tuple[str, str]] = []

    graph = {fm.relative_path: fm.dependencies for fm in files}

    for fm in files:
        if len(fm.dependents) >= 3:
            monolithic_files.append({
                "file": fm.relative_path,
                "dependents": len(fm.dependents),
                "suggestion": (
                    f"{fm.name} is imported by {len(fm.dependents)} files. "
                    f"Changes here ripple widely — consider narrowing its public API."
                ),
            })

        if not fm.dependencies and not fm.dependents:
            purpose = fm.purpose or ""
            if purpose != "🚀 Entry Point" and "test" not in purpose.lower():
                dead_files.append({
                    "file": fm.relative_path,
                    "suggestion": "Disconnected from the rest of the codebase.",
                })

        for dep in fm.dependencies:
            if dep in graph and fm.relative_path in graph[dep]:
                pair = tuple(sorted([fm.relative_path, dep]))
                if pair not in circular_deps:
                    circular_deps.append(pair)

    cross_cutting = cross_cutting_files(project, threshold=3)
    split_candidates = project_split_candidates(project, top_n=8)

    summary_parts = [f"Analyzed {len(files)} files"]
    if monolithic_files:
        summary_parts.append(f"{len(monolithic_files)} highly coupled")
    if circular_deps:
        summary_parts.append(f"{len(circular_deps)} circular")
    if cross_cutting:
        summary_parts.append(f"{len(cross_cutting)} cross-cutting")
    if split_candidates:
        summary_parts.append(f"{len(split_candidates)} split candidates")
    summary = ", ".join(summary_parts) + "."

    return {
        "summary": summary,
        "monolithic_files": monolithic_files,
        "circular_dependencies": [
            {
                "files": list(pair),
                "suggestion": (
                    f"Tight coupling between {pair[0]} and {pair[1]}. "
                    f"Extract the shared symbols into a third module."
                ),
            } for pair in circular_deps
        ],
        "dead_files": dead_files,
        "cross_cutting_files": cross_cutting,
        "split_candidates": split_candidates,
    }
