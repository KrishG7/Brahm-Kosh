"""
Smart Architect Analyzer for Brahm-Kosh.

Scans the Lexical Dependency Graph for structural anti-patterns
(God classes, circular dependencies, dead code).
"""

from typing import Any, Dict, List, Tuple
from brahm_kosh.models import Project, FileModel


def analyze_structure(project: Project) -> Dict[str, Any]:
    """
    Analyzes the project structural graph and returns an AI-like suggestion payload.
    """
    files: List[FileModel] = project.all_files()
    
    god_files = []
    dead_files = []
    circular_deps = []
    
    # Simple dependency graph cache for circular detection
    graph = {fm.relative_path: fm.dependencies for fm in files}
    
    for fm in files:
        # Detect God Classes/Files (Too many incoming links)
        # Using a low threshold for the sandbox, realistically > 10
        if len(fm.dependents) >= 3:
            god_files.append({
                "file": fm.relative_path,
                "dependents": len(fm.dependents),
                "suggestion": f"This file is highly coupled. Consider breaking {fm.name} into smaller interfaces."
            })
            
        # Detect Dead Code (No incoming and no outgoing, outside of entry points)
        if len(fm.dependencies) == 0 and len(fm.dependents) == 0:
            if fm.purpose != "🚀 Entry Point" and "test" not in fm.purpose.lower():
                dead_files.append({
                    "file": fm.relative_path,
                    "suggestion": f"This file appears completely disconnected from the rest of the codebase."
                })
                
        # Detect Circular Dependencies (A -> B and B -> A)
        for dep in fm.dependencies:
            if dep in graph and fm.relative_path in graph[dep]:
                # To prevent duplicates like A<->B and B<->A, sort them
                pair = tuple(sorted([fm.relative_path, dep]))
                if pair not in circular_deps:
                    circular_deps.append(pair)

    return {
        "summary": f"Analyzed {len(files)} files and found {len(god_files)} highly coupled nodes and {len(circular_deps)} circular dependencies.",
        "god_files": god_files,
        "circular_dependencies": [
            {
                "files": list(pair),
                "suggestion": f"Tight coupling detected between {pair[0]} and {pair[1]}. Use a shared common module or dependency injection."
            } for pair in circular_deps
        ],
        "dead_files": dead_files
    }
