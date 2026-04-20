# Brahm-Kosh

> **Codebase Intelligence Engine**
> Turns code into structure, structure into insight, and insight into confidence.

---

## What Is This?

Brahm-Kosh is not a linter, not a code formatter, not Copilot.

It is a **codebase understanding engine** built around one belief:

> Humans understand systems visually and structurally — not line by line.

Run it on any Python repo. Instead of randomly clicking files, you instantly see:

- 📁 **Hierarchical structure** — projects, modules, files, symbols
- 🔥 **Complexity scoring** — every function and file scored 0–100
- 🔴🟠🟡🟢 **Heat-mapped hotspots** — "where do I look first?"
- 🎯 **Purpose inference** — "what is this file for?"

## Installation

```bash
cd Brahm-Kosh
pip install -e .
```

## Usage

### Visual Analysis (default)

```bash
brahm-kosh analyze .
brahm-kosh analyze /path/to/repo
brahm-kosh analyze . --top 20
```

### JSON Output

```bash
brahm-kosh analyze . --json
```

## Architecture

```
brahm_kosh/
├── models.py          # Universal code model (language-agnostic)
├── engine.py          # Orchestrator: parse → score → rank → infer
├── cli.py             # Rich CLI output
├── adapters/
│   └── python_adapter.py  # Python AST parser
└── analysis/
    ├── complexity.py  # Structural complexity scoring
    ├── hotspots.py    # Top-N hotspot ranking
    └── purpose.py     # File purpose inference
```

**Philosophy: One brain, many languages.**

The universal code model (`Project → Module → File → Symbol`) is language-agnostic. Language adapters are pluggable. Today it's Python. Tomorrow: JS, Java, C/C++.

## Complexity Scoring

Not just a tree. A **weighted tree**.

Each symbol is scored on:

| Factor | Weight | What It Measures |
|--------|--------|------------------|
| Line count | 20% | Length → more to read |
| Nesting depth | 30% | Depth → harder to follow |
| Branch count | 30% | Branches → more paths |
| Call count | 20% | Coupling → more dependencies |

Files are scored as 60% average + 40% max (hotspot pull).

## The Vision

**v0.1** (now): Structural awareness — the mirror.
**v1.0**: Architectural awareness — dependency graphs, circular imports, impact simulation.
**v2.0**: Predictive awareness — git churn, error propagation, drift detection.

---

*A student opens a massive repo. Runs `brahm-kosh analyze .`. And instead of fear… they feel: "Oh." That's the win.*
