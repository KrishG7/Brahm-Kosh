"""
Multi-hop impact analysis.

Given a file, walks the dependency graph in both directions to answer:
  - "Who transitively depends on this file?"  (upstream — files that BREAK
    if this file's interface changes)
  - "What does this file transitively depend on?"  (downstream — files
    this one relies on through any number of hops)

This is the algorithmic answer to "if I change A, what's affected?" A
single-edge view (direct dependents only) misses Z importing Y importing
X importing A. BFS surfaces the closure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from brahm_kosh.models import Project


@dataclass
class ImpactSet:
    """Result of an impact computation, broken down by hop distance."""

    direct: list[str]                    # 1-hop neighbors
    indirect: list[str]                  # 2+ hops
    by_hop: dict[int, list[str]]         # hop level -> files
    total: list[str]                     # everything but the source file

    @property
    def total_count(self) -> int:
        return len(self.total)

    @property
    def max_depth(self) -> int:
        return max(self.by_hop.keys()) if self.by_hop else 0

    def to_dict(self) -> dict:
        return {
            "direct": self.direct,
            "indirect": self.indirect,
            "by_hop": {str(k): v for k, v in sorted(self.by_hop.items())},
            "total": self.total,
            "total_count": self.total_count,
            "max_depth": self.max_depth,
        }


def _bfs(start: str, edges: dict[str, list[str]], max_depth: Optional[int] = None) -> dict[int, list[str]]:
    """BFS from `start` returning hop-level → list of nodes at that hop."""
    visited: set[str] = {start}
    by_hop: dict[int, list[str]] = {}
    queue: deque[tuple[str, int]] = deque([(start, 0)])

    while queue:
        node, depth = queue.popleft()
        next_depth = depth + 1
        if max_depth is not None and next_depth > max_depth:
            continue
        for neighbor in edges.get(node, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            by_hop.setdefault(next_depth, []).append(neighbor)
            queue.append((neighbor, next_depth))

    return by_hop


def compute_upstream_impact(
    file_path: str,
    project: Project,
    max_depth: Optional[int] = None,
) -> ImpactSet:
    """
    Files that transitively import `file_path`.

    These break (compile errors, runtime errors, broken expectations) if
    the file's public interface changes. This is the answer to "what's
    the blast radius of changing A?"
    """
    # Edges: file -> [files that import it]
    edges: dict[str, list[str]] = {fm.relative_path: list(fm.dependents) for fm in project.all_files()}
    return _build_set(file_path, edges, max_depth)


def compute_downstream_impact(
    file_path: str,
    project: Project,
    max_depth: Optional[int] = None,
) -> ImpactSet:
    """
    Files this file transitively depends on.

    Useful for "if I want to truly understand A, what other code do I
    need to read?" or "what's the minimum set of files A pulls in?"
    """
    edges: dict[str, list[str]] = {fm.relative_path: list(fm.dependencies) for fm in project.all_files()}
    return _build_set(file_path, edges, max_depth)


def _build_set(start: str, edges: dict[str, list[str]], max_depth: Optional[int]) -> ImpactSet:
    by_hop = _bfs(start, edges, max_depth)
    direct = list(by_hop.get(1, []))
    indirect: list[str] = []
    total: list[str] = []
    for hop, nodes in sorted(by_hop.items()):
        total.extend(nodes)
        if hop > 1:
            indirect.extend(nodes)
    return ImpactSet(direct=direct, indirect=indirect, by_hop=by_hop, total=total)


def compute_full_impact(file_path: str, project: Project) -> dict:
    """Both directions, ready to ship as a JSON payload."""
    up = compute_upstream_impact(file_path, project)
    down = compute_downstream_impact(file_path, project)
    return {
        "path": file_path,
        "upstream": up.to_dict(),    # who is affected if you change this
        "downstream": down.to_dict(),  # what this transitively reads
    }
