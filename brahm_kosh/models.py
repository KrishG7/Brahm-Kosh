"""
Universal Code Model for Brahm-Kosh.

Language-agnostic data structures that every adapter feeds into.
This is the brain — one model, many languages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SymbolKind(str, Enum):
    """The kind of code symbol."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"


@dataclass
class Symbol:
    """
    A single code symbol: function, class, or method.

    This is the atomic unit of Brahm-Kosh's understanding.
    """

    name: str
    kind: SymbolKind
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    calls: list[str] = field(default_factory=list)
    children: list[Symbol] = field(default_factory=list)
    complexity: float = 0.0
    nesting_depth: int = 0
    branch_count: int = 0
    purpose: Optional[str] = None

    @property
    def line_count(self) -> int:
        return self.line_end - self.line_start + 1

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
        d = {
            "name": self.name,
            "kind": self.kind.value,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "line_count": self.line_count,
            "complexity": round(self.complexity, 1),
            "heat": self.heat_label,
            "nesting_depth": self.nesting_depth,
            "branch_count": self.branch_count,
        }
        if self.docstring:
            d["docstring"] = self.docstring
        if self.calls:
            d["calls"] = self.calls
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        if self.purpose:
            d["purpose"] = self.purpose
        return d


@dataclass
class FileModel:
    """
    Represents a single source file in the project.
    """

    name: str
    path: str
    relative_path: str
    line_count: int = 0
    symbols: list[Symbol] = field(default_factory=list)
    complexity: float = 0.0
    purpose: Optional[str] = None

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

    @property
    def symbol_count(self) -> int:
        count = len(self.symbols)
        for s in self.symbols:
            count += len(s.children)
        return count

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "relative_path": self.relative_path,
            "line_count": self.line_count,
            "symbol_count": self.symbol_count,
            "complexity": round(self.complexity, 1),
            "heat": self.heat_label,
        }
        if self.purpose:
            d["purpose"] = self.purpose
        if self.symbols:
            d["symbols"] = [s.to_dict() for s in self.symbols]
        return d


@dataclass
class Module:
    """
    A module (directory/package) in the project.
    """

    name: str
    path: str
    relative_path: str
    files: list[FileModel] = field(default_factory=list)
    submodules: list[Module] = field(default_factory=list)

    @property
    def total_lines(self) -> int:
        lines = sum(f.line_count for f in self.files)
        lines += sum(m.total_lines for m in self.submodules)
        return lines

    @property
    def total_files(self) -> int:
        count = len(self.files)
        count += sum(m.total_files for m in self.submodules)
        return count

    @property
    def total_symbols(self) -> int:
        count = sum(f.symbol_count for f in self.files)
        count += sum(m.total_symbols for m in self.submodules)
        return count

    @property
    def avg_complexity(self) -> float:
        all_files = self._all_files()
        if not all_files:
            return 0.0
        return sum(f.complexity for f in all_files) / len(all_files)

    def _all_files(self) -> list[FileModel]:
        files = list(self.files)
        for m in self.submodules:
            files.extend(m._all_files())
        return files

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "relative_path": self.relative_path,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_symbols": self.total_symbols,
            "avg_complexity": round(self.avg_complexity, 1),
        }
        if self.files:
            d["files"] = [f.to_dict() for f in self.files]
        if self.submodules:
            d["submodules"] = [m.to_dict() for m in self.submodules]
        return d


@dataclass
class Metadata:
    """Project-level metadata summary."""

    total_files: int = 0
    total_lines: int = 0
    total_symbols: int = 0
    total_modules: int = 0
    languages: list[str] = field(default_factory=list)
    avg_complexity: float = 0.0
    max_complexity_file: Optional[str] = None
    max_complexity_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_symbols": self.total_symbols,
            "total_modules": self.total_modules,
            "languages": self.languages,
            "avg_complexity": round(self.avg_complexity, 1),
            "max_complexity_file": self.max_complexity_file,
            "max_complexity_score": round(self.max_complexity_score, 1),
        }


@dataclass
class Project:
    """
    The root of the Brahm-Kosh code model.

    Everything flows into and out of this structure.
    """

    name: str
    path: str
    modules: list[Module] = field(default_factory=list)
    root_files: list[FileModel] = field(default_factory=list)
    metadata: Metadata = field(default_factory=Metadata)

    def all_files(self) -> list[FileModel]:
        """Flatten all files across all modules."""
        files = list(self.root_files)
        for m in self.modules:
            files.extend(m._all_files())
        return files

    def all_symbols(self) -> list[tuple[str, Symbol]]:
        """Flatten all symbols, returned as (file_path, symbol) tuples."""
        results = []
        for f in self.all_files():
            for s in f.symbols:
                results.append((f.relative_path, s))
                for child in s.children:
                    results.append((f.relative_path, child))
        return results

    def compute_metadata(self) -> None:
        """Recompute metadata from current model state."""
        all_files = self.all_files()
        self.metadata.total_files = len(all_files)
        self.metadata.total_lines = sum(f.line_count for f in all_files)
        self.metadata.total_symbols = sum(f.symbol_count for f in all_files)
        self.metadata.total_modules = len(self.modules)
        self.metadata.languages = list(set(self.metadata.languages)) or ["Python"]

        if all_files:
            self.metadata.avg_complexity = (
                sum(f.complexity for f in all_files) / len(all_files)
            )
            most_complex = max(all_files, key=lambda f: f.complexity)
            self.metadata.max_complexity_file = most_complex.relative_path
            self.metadata.max_complexity_score = most_complex.complexity

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "path": self.path,
            "metadata": self.metadata.to_dict(),
        }
        if self.root_files:
            d["root_files"] = [f.to_dict() for f in self.root_files]
        if self.modules:
            d["modules"] = [m.to_dict() for m in self.modules]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
