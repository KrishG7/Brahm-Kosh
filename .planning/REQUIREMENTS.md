# Brahm-Kosh v1.0 — Requirements

## Mission

Ship Brahm-Kosh as a genuinely useful, multi-language codebase intelligence engine. Anyone with a repo — Python, JavaScript, C — runs one command and gets instant structural insight.

---

## Must-Have (MVP for v1.0)

### Language Support
- **M1** — JavaScript/TypeScript adapter: parse `.js`, `.ts`, `.jsx`, `.tsx`, extract functions, classes, arrow function assignments, async functions
- **M2** — C/C++ adapter: parse `.c`, `.cpp`, `.h`, `.hpp`, extract functions and structs
- **M3** — Multi-language project support: a single `brahm-kosh analyze .` discovers and runs all applicable adapters

### Engine
- **M4** — Auto-discover registered adapters (remove hard-coded `python` lookup in `engine.py`)
- **M5** — Language detection: scan directory, detect languages present, route to correct adapters
- **M6** — Per-language metadata in output: show file count and line count broken down by language

### CLI
- **M7** — `--lang` flag: `brahm-kosh analyze . --lang python` targets a specific adapter
- **M8** — Language breakdown in CLI stats panel (e.g., "Python: 12 files, JS: 8 files")

### Polish
- **M9** — Python adapter fine-tuning: improved purpose inference (fix false-positive "utility" labels), better handling of empty files and single-function files
- **M10** — Version bump: `pyproject.toml` → `1.0.0`, `__version__` → `1.0.0`, README updated

---

## Should-Have (if time permits)

- **S1** — Go adapter: parse `.go` files, extract functions and methods (lightweight regex-based)
- **S2** — Rust adapter: parse `.rs` files, extract `fn` and `struct` definitions
- **S3** — `brahm-kosh list-adapters` command: show registered adapters and their supported extensions

---

## Won't Have (v1.0)

- Dependency/import graph analysis
- Git churn data
- AI summaries
- Web UI

---

## Acceptance Criteria

| Requirement | Test |
|---|---|
| M1 JS/TS adapter | `brahm-kosh analyze <js-repo>` correctly parses functions/classes |
| M2 C/C++ adapter | `brahm-kosh analyze <c-project>` extracts functions with line numbers |
| M3 Multi-language | `brahm-kosh analyze <mixed-repo>` shows modules from multiple languages |
| M4 Auto-discover | No `import python_adapter` hard-code in engine.py |
| M5 Language detect | Stats panel shows detected languages correctly |
| M7 `--lang` flag | `--lang python` limits analysis to Python files only |
| M9 Purpose tuning | Common Python stdlib patterns classified correctly |
| M10 Version | `brahm-kosh --version` returns `1.0.0` |
