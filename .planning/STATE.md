# Brahm-Kosh — Project State

## Current Position

**Milestone:** v1.0 — Multi-Language Intelligence Engine
**Current Phase:** Phase 1 — Engine Refactor & Python Fine-Tuning
**Status:** Not started

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
