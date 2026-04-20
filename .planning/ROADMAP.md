# Brahm-Kosh v1.0 — Roadmap

## Milestone: v1.0 — Multi-Language Intelligence Engine

**Goal:** Extend Brahm-Kosh from Python-only to a genuinely multi-language codebase tool — JavaScript/TypeScript, C/C++, and engine improvements — while fine-tuning the existing Python adapter.

---

## Phase 1 — Engine Refactor & Python Fine-Tuning

**Goal:** Decouple the engine from Python-specific assumptions and polish the existing Python adapter before adding new languages.

**Dependencies:** None (start here)

**Deliverables:**
- 1A — Engine auto-discovery: remove hard-coded `get_adapter("python")` from `engine.py`; introduce `analyze_path(path)` that detects languages and routes to the right adapters automatically
- 1B — `--lang` CLI flag: add `brahm-kosh analyze . --lang python|javascript|c` for explicit filtering
- 1C — Python purpose inference improvements: fix over-classification of small utility files; add recognition for test files, config files, migration scripts
- 1D — Version bump: `pyproject.toml → 1.0.0`, `__version__ → 1.0.0`

**UAT criteria:**
- `brahm-kosh analyze .` (on brahm-kosh itself) works without changes
- `brahm-kosh analyze . --lang python` works identically to current behavior
- `brahm-kosh --version` returns `1.0.0`
- Purpose labels on `cli.py`, `engine.py`, `models.py` are sensible

---

## Phase 2 — JavaScript/TypeScript Adapter

**Goal:** Add JS/TS support using a pure-Python approach (regex + simple parse) or bundled `tree-sitter` bindings.

**Dependencies:** Phase 1 complete

**Deliverables:**
- 2A — JS/TS adapter (`brahm_kosh/adapters/javascript_adapter.py`): supports `.js`, `.ts`, `.jsx`, `.tsx`
  - Extract: named functions, arrow function assignments, classes and their methods
  - Complexity scoring: line count, nesting (if/for/while/try), call sites
  - Auto-register via `register_adapter("javascript", ...)`
- 2B — Language detection update: detect `.js/.ts/.jsx/.tsx` files and load JS adapter
- 2C — CLI stats panel: breakdown by language (e.g., "Python: 12 files | JS: 8 files")
- 2D — Hotspot table: add `Language` column showing which adapter produced each hotspot

**Approach:** Use Python `re` module for JS parsing (avoids Node.js dependency). Target well-structured code — arrow functions, classes, named functions. Skip advanced macro/decorator patterns.

**UAT criteria:**
- `brahm-kosh analyze <react-project>` extracts components and hooks
- `brahm-kosh analyze <node-project>` extracts express routes, middleware functions
- Complexity scoring ranks deeply nested callbacks higher than simple one-liners
- No crash on `.tsx` files with JSX syntax

---

## Phase 3 — C/C++ Adapter

**Goal:** Parse C and C++ source files and extract functions and structs.

**Dependencies:** Phase 1 complete (Phase 2 can run in parallel)

**Deliverables:**
- 3A — C/C++ adapter (`brahm_kosh/adapters/c_adapter.py`): supports `.c`, `.cpp`, `.h`, `.hpp`
  - Extract: function definitions (with return type, name, params), struct/class declarations
  - Complexity scoring: line count, if/for/while/switch branches, nesting depth
  - Auto-register via `register_adapter("c", ...)`
- 3B — Language detection update: detect `.c/.cpp/.h/.hpp` files and load C adapter
- 3C — Skip: preprocessor macros, inline assembly — mark as unparseable symbols

**Approach:** Regex-based parsing targeting the common C function definition pattern `type name(params) {`. Handles 80% of real-world C code without a compiler dependency.

**UAT criteria:**
- `brahm-kosh analyze <linux-kernel-subsystem>` extracts functions
- `brahm-kosh analyze <simple-c-project>` shows file tree with hotspots
- Struct declarations appear as CLASS-kind symbols
- Header files (`.h`) show function signatures (declarations)

---

## Phase 4 — Multi-Language Integration & Final Polish

**Goal:** Make the full multi-language experience seamless. Polish output and ship v1.0.

**Dependencies:** Phase 2 + Phase 3

**Deliverables:**
- 4A — Multi-adapter engine run: `analyze_path` runs all applicable adapters and merges results into one `Project` model
- 4B — Per-language module grouping in tree: modules grouped by language when multiple present
- 4C — `brahm-kosh list-adapters` command: show registered adapters and supported extensions
- 4D — README v1.0: update with JS/C examples, multi-language demo, architecture diagram
- 4E — `pyproject.toml`: finalize v1.0.0 metadata (classifiers, keywords, homepage)
- 4F — Verify full end-to-end on 3 real repos: a Python library, a JS/React app, a C command-line tool

**UAT criteria:**
- `brahm-kosh analyze <mixed-repo>` shows modules from multiple languages in one tree
- Stats panel shows correct per-language file counts
- `brahm-kosh list-adapters` prints: `python (.py), javascript (.js .ts .jsx .tsx), c (.c .cpp .h .hpp)`
- No crashes on any of the 3 test repos
- README is accurate and complete

---

## Phase Summary

| Phase | Name | Status |
|-------|------|--------|
| 1 | Engine Refactor & Python Fine-Tuning | ✅ Complete |
| 2 | JavaScript/TypeScript Adapter | ✅ Complete |
| 3 | C/C++ Adapter | ✅ Complete |
| 4 | Multi-Language Integration & Polish | 🔲 Not started |
