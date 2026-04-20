"""
Hotspot Ranking Engine for Brahm-Kosh.

Ranks all symbols across the project by complexity score.
Returns the top hotspots — the places that need the most attention.
"""

from __future__ import annotations

from dataclasses import dataclass

from brahm_kosh.models import Project, Symbol


@dataclass
class Hotspot:
    """A ranked hotspot — a symbol that demands attention."""

    rank: int
    file_path: str
    symbol_name: str
    symbol_kind: str
    language: str
    complexity: float
    line_start: int
    line_end: int
    line_count: int

    @property
    def heat_label(self) -> str:
        if self.complexity >= 80:
            return "Critical"
        elif self.complexity >= 60:
            return "High"
        elif self.complexity >= 40:
            return "Medium"
        else:
            return "Low"

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "file": self.file_path,
            "symbol": self.symbol_name,
            "kind": self.symbol_kind,
            "language": self.language,
            "complexity": round(self.complexity, 1),
            "heat": self.heat_label,
            "lines": f"{self.line_start}-{self.line_end}",
            "line_count": self.line_count,
        }


def find_hotspots(project: Project, top_n: int = 10) -> list[Hotspot]:
    """
    Find the top-N most complex symbols in the project.
    """
    all_symbols = project.all_symbols()

    # Sort by complexity descending. Note x[2] is the symbol due to tuple structure.
    all_symbols.sort(key=lambda x: x[2].complexity, reverse=True)

    hotspots = []
    for i, (file_path, language, sym) in enumerate(all_symbols[:top_n]):
        hotspots.append(
            Hotspot(
                rank=i + 1,
                file_path=file_path,
                symbol_name=sym.name,
                symbol_kind=sym.kind.value,
                language=language,
                complexity=sym.complexity,
                line_start=sym.line_start,
                line_end=sym.line_end,
                line_count=sym.line_count,
            )
        )

    return hotspots
