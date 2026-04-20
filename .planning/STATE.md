# Brahm-Kosh — Project State

## Current Position

**Milestone:** v1.0 — Multi-Language Intelligence Engine
**Current Phase:** None
**Status:** ✅ Complete

### Recent Changes
* **Phase 1:** Refactored engine to support auto-discovery of languages. Added `--lang` flag and `list-adapters` command. Enhanced Python purpose inference heuristics (5-layer system).
* **Phase 2:** Implemented pure-Python, regex-based JavaScript/TypeScript adapter. Extracts async/arrow/class methods and calculates complexity.
* **Phase 3:** Implemented pure-Python, regex-based C/C++ adapter. Extracts C functions, C++ structs/classes/methods and calculates complexity.
* **Phase 4:** Integrated multi-language metadata into CLI. Added `Language` column to the hotspots table and a language breakdown in the stats panel. Updated `README.md`. Bumped version to 1.0.0.

---

## Decisions

| Decision | Rationale |
|---|---|
| JS adapter: pure Python regex | Avoids Node.js runtime dependency; simpler install story |
| C adapter: regex-based | No compiler dependency; covers 80% of real-world C |
| Engine auto-discovery over hard-coded python | Extensibility — adding a language = adding an adapter file only |
| Granularity: standard | 4 phases, clear separation of concerns |
| Model profile: balanced | Good quality/cost for this scope |

---

## Blockers

(None)

---

## Notes

- v0.1 is working and committed to git (initial commit)
- `venv/` and `__pycache__/` excluded via `.gitignore`
- Python adapter uses stdlib `ast` — zero external deps for Python analysis
- JS adapter will use `re` only — keep install simple
- Test repo candidates: numpy (Python), React repo (JS), SQLite or curl (C)

---
*Initialized: 2026-04-20*
