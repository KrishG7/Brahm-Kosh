"""
Refactor Suggestion Engine.

For files that look "too big" (high complexity, many symbols, many
domains), this module looks at the within-file call graph and asks:
"Is there a clean split point?"

The rule of thumb: if the symbols inside a file fall into multiple
disconnected components — group A's functions all call each other but
nothing in group B — those are obvious split candidates. The file is
already two modules pretending to be one.

The output isn't "rewrite this for me." It's "here's a partition that
respects existing call relationships; consider extracting it."
"""

from __future__ import annotations

from dataclasses import dataclass

from brahm_kosh.models import FileModel, Symbol, SymbolKind


# A class containing methods is treated as one node — we don't split
# classes apart. Only top-level symbols become graph nodes.
def _file_top_level_symbols(file_model: FileModel) -> list[Symbol]:
    return list(file_model.symbols)


def _calls_inside(symbol: Symbol) -> set[str]:
    """All call-target names appearing in `symbol` and its method children."""
    out = set(symbol.calls or [])
    for child in symbol.children or []:
        out.update(_calls_inside(child))
    return out


# ---------------------------------------------------------------------------
# Union-find — keeps the connected-component logic in 12 lines.
# ---------------------------------------------------------------------------

class _DSU:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


# ---------------------------------------------------------------------------
# Cluster suggestion
# ---------------------------------------------------------------------------

@dataclass
class Cluster:
    members: list[str]              # symbol names
    suggested_purpose: str
    representative_lines: tuple[int, int]  # spans the union of member ranges

    def to_dict(self) -> dict:
        return {
            "members": self.members,
            "suggested_purpose": self.suggested_purpose,
            "line_start": self.representative_lines[0],
            "line_end": self.representative_lines[1],
            "size": len(self.members),
        }


_PURPOSE_HINTS = [
    # (substring → purpose label)
    ("test", "tests"),
    ("parse", "parsing"),
    ("render", "rendering"),
    ("score", "scoring"),
    ("compute", "computation"),
    ("save", "persistence"),
    ("load", "loading"),
    ("validate", "validation"),
    ("send", "I/O"),
    ("read", "I/O"),
    ("write", "I/O"),
    ("format", "formatting"),
    ("build", "construction"),
    ("init", "initialisation"),
]


def _infer_cluster_purpose(symbols: list[Symbol]) -> str:
    """Best-effort label for a cluster — uses the dominant verb in member names."""
    if not symbols:
        return "misc"
    blob = " ".join(s.name.lower() for s in symbols)
    for hint, label in _PURPOSE_HINTS:
        if hint in blob:
            return label
    # Fallback — use the first symbol kind as a rough label
    kinds = {s.kind for s in symbols}
    if SymbolKind.CLASS in kinds:
        return "data model"
    return "helpers"


def suggest_splits(file_model: FileModel, min_symbols: int = 4) -> list[Cluster]:
    """
    Return a list of clusters representing a recommended file partition.

    If the file has fewer than `min_symbols` symbols or only one connected
    component, the result is empty (no split worthwhile).
    """
    symbols = _file_top_level_symbols(file_model)
    if len(symbols) < min_symbols:
        return []

    # Map symbol name → symbol for quick edges
    by_name = {s.name: s for s in symbols}
    if len(by_name) < min_symbols:
        return []  # name collisions

    dsu = _DSU(by_name.keys())

    # Edge: a symbol that calls another in the same file → union them
    for s in symbols:
        for callee in _calls_inside(s):
            if callee in by_name and callee != s.name:
                dsu.union(s.name, callee)

    # Group symbols by their root
    groups: dict[str, list[Symbol]] = {}
    for s in symbols:
        root = dsu.find(s.name)
        groups.setdefault(root, []).append(s)

    # Keep only components with >= 1 symbol; if there's only one, no split
    components = [g for g in groups.values() if g]
    if len(components) <= 1:
        return []

    # Drop singleton components — splitting off one helper isn't useful
    multi = [c for c in components if len(c) >= 2]
    if not multi or len(multi) < 2:
        return []

    clusters: list[Cluster] = []
    for group in sorted(multi, key=lambda g: -len(g)):
        line_start = min(s.line_start for s in group)
        line_end = max(s.line_end for s in group)
        clusters.append(Cluster(
            members=[s.name for s in group],
            suggested_purpose=_infer_cluster_purpose(group),
            representative_lines=(line_start, line_end),
        ))
    return clusters


def project_split_candidates(project, top_n: int = 8) -> list[dict]:
    """Find the top files that would benefit most from a split, with the splits described."""
    out = []
    for fm in project.all_files():
        clusters = suggest_splits(fm)
        if len(clusters) >= 2:
            out.append({
                "file": fm.relative_path,
                "complexity": round(fm.complexity, 1),
                "heat": fm.heat_label,
                "clusters": [c.to_dict() for c in clusters],
                "summary": (
                    f"{fm.name} contains {len(clusters)} disconnected groups "
                    f"({', '.join(c.suggested_purpose for c in clusters)}) — "
                    f"these never call each other."
                ),
            })
    # Worst offenders first — by complexity then by cluster count
    out.sort(key=lambda x: (-x["complexity"], -len(x["clusters"])))
    return out[:top_n]
