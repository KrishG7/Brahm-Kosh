# Brahm-Kosh — Project Context

## What This Is

**Brahm-Kosh** is a codebase intelligence engine — a CLI tool that turns any source code repository into a structured, scored, visual map. It answers the question "where do I look first?" by computing structural complexity, ranking hotspots, and inferring the purpose of each file.

**Core belief:** Humans understand systems visually and structurally — not line by line.

**Target users:** Developers onboarding to unfamiliar codebases, students studying real-world projects, engineers doing code reviews or audits.

**Current state (v0.1):** Python-only. Works end-to-end with Rich CLI, complexity scoring, hotspot ranking, and purpose inference.

**This milestone (v1.0):** Multi-language analysis engine. Add JavaScript/TypeScript and C/C++ adapters. Refine the engine. Polish the CLI. Ship as a genuinely useful tool beyond Python repos.

---

## Core Value

A developer opens a massive, unfamiliar repo. Runs `brahm-kosh analyze .`. Instead of fear — they feel: *"Oh. Now I see it."*

That moment of clarity is the product.

---

## Requirements

### Validated (v0.1 — existing)

- ✓ Universal language-agnostic code model (`Project → Module → File → Symbol`)
- ✓ Python adapter using AST — parses functions, classes, methods
- ✓ Structural complexity scoring (line count, nesting depth, branches, calls) on 0-100 scale
- ✓ Hotspot ranking (top-N highest complexity symbols)
- ✓ File purpose inference from naming + symbol patterns
- ✓ Rich CLI visual tree with heat-mapped output
- ✓ JSON output mode (`--json`) for programmatic use
- ✓ Pluggable adapter registry (`register_adapter`)

### Active (v1.0 targets)

- [ ] **JavaScript/TypeScript adapter** — parse JS/TS files, extract functions, classes, arrow functions; handle JSX/TSX
- [ ] **C/C++ adapter** — parse .c, .cpp, .h files; extract functions and structs using regex or tree-sitter
- [ ] **Multi-language project support** — single `brahm-kosh analyze .` runs all applicable adapters
- [ ] **Language detection** — auto-detect which languages are present; display breakdown in stats
- [ ] **Engine decoupling** — engine.py should not hard-code `python` adapter; auto-discover registered adapters
- [ ] **Python v0.1 fine-tuning** — improve purpose inference accuracy, fix edge cases in complexity scoring
- [ ] **CLI `--lang` flag** — allow user to target a specific language adapter explicitly
- [ ] **Version bump to 1.0.0** — update pyproject.toml, `__version__`, README

### Out of Scope (v1.0)

- Dependency graph / import graph analysis — v1.5+
- Git churn integration — v2.0
- AI/LLM-powered summaries — v2.0
- Language Server Protocol (LSP) integration — future
- Web UI / dashboard — future

---

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Python AST for Python adapter | Zero dependencies, exact line numbers, robust | ✓ Proven in v0.1 |
| Pluggable adapter registry | Enables language-by-language extension without engine changes | ✓ Implemented |
| JavaScript: use `@babel/parser` or `tree-sitter-javascript` | Handles JSX/TSX, async, modern syntax | Pending — to decide in Phase 2 |
| C/C++: regex-based or tree-sitter | tree-sitter-c is more robust; regex is simpler but fragile on macros | Pending — Phase 3 |
| Single `brahm-kosh analyze .` for all languages | UX simplicity — one command works everywhere | Committed |
| `.planning/` committed to git | Track planning evolution | Yes |

---

## Context

- **Language:** Python 3.9+ (the tool itself; it analyzes many languages)
- **Dependencies:** `click>=8.0`, `rich>=13.0`; add language-specific parsers per adapter
- **Install:** `pip install -e .` (editable install from pyproject.toml)
- **Entry point:** `brahm-kosh analyze [PATH]`
- **File structure:** `brahm_kosh/adapters/` for language adapters, `brahm_kosh/analysis/` for analysis passes

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:** Update requirements (validate, scope out, add new), log decisions.
**After milestone:** Full review, vision check, architecture reassessment.

---
*Last updated: 2026-04-20 after initialization — v1.0 milestone begins*
