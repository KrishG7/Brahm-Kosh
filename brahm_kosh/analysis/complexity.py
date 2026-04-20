"""
Complexity Scoring Engine for Brahm-Kosh.

Computes structural complexity for every symbol and file.
Normalized to a 0–100 scale.

Factors:
  - Line count (longer = more complex)
  - Nesting depth (deeper = harder to reason about)
  - Branch count (more branches = more cognitive load)
  - Call count (more outgoing calls = more coupling)
"""

from __future__ import annotations

from brahm_kosh.models import FileModel, Project, Symbol


# Weights for the complexity formula
WEIGHT_LINES = 0.20
WEIGHT_NESTING = 0.30
WEIGHT_BRANCHES = 0.30
WEIGHT_CALLS = 0.20

# Normalization baselines (what counts as "very high")
MAX_LINES = 100        # 100+ lines = maxed out
MAX_NESTING = 6        # 6+ levels deep = maxed out
MAX_BRANCHES = 15      # 15+ branches = maxed out
MAX_CALLS = 20         # 20+ calls = maxed out


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def score_symbol(symbol: Symbol) -> float:
    """
    Compute a 0-100 complexity score for a single symbol.
    """
    line_score = min(symbol.line_count / MAX_LINES, 1.0) * 100
    nesting_score = min(symbol.nesting_depth / MAX_NESTING, 1.0) * 100
    branch_score = min(symbol.branch_count / MAX_BRANCHES, 1.0) * 100
    call_score = min(len(symbol.calls) / MAX_CALLS, 1.0) * 100

    raw = (
        WEIGHT_LINES * line_score
        + WEIGHT_NESTING * nesting_score
        + WEIGHT_BRANCHES * branch_score
        + WEIGHT_CALLS * call_score
    )

    return _clamp(raw)


def score_file(file_model: FileModel) -> float:
    """
    Compute a 0-100 complexity score for a file.

    File score = weighted average of symbol scores,
    boosted by number of symbols and total lines.
    """
    if not file_model.symbols:
        # Files with no symbols get a basic line-count score
        return _clamp(min(file_model.line_count / MAX_LINES, 1.0) * 30)

    # Score all symbols (including methods inside classes)
    all_scores = []
    for sym in file_model.symbols:
        all_scores.append(sym.complexity)
        for child in sym.children:
            all_scores.append(child.complexity)

    if not all_scores:
        return 0.0

    avg_score = sum(all_scores) / len(all_scores)
    max_score = max(all_scores)

    # File score = 60% average + 40% max (hotspot pull)
    file_score = 0.6 * avg_score + 0.4 * max_score

    # Slight boost for files with many symbols (more cognitive load)
    symbol_count = len(all_scores)
    if symbol_count > 10:
        file_score = min(file_score * 1.15, 100.0)
    elif symbol_count > 5:
        file_score = min(file_score * 1.05, 100.0)

    return _clamp(file_score)


def score_project(project: Project) -> None:
    """
    Score every symbol and file in the project (mutates in place).
    """
    for file_model in project.all_files():
        # Score individual symbols first
        for sym in file_model.symbols:
            sym.complexity = score_symbol(sym)
            for child in sym.children:
                child.complexity = score_symbol(child)

        # Then score the file based on its symbols
        file_model.complexity = score_file(file_model)
