# Brahm-Kosh

> **Codebase Intelligence Engine.**
> Reads source code without running it. Tells you the structure, the
> hotspots, the cross-cutting concerns, and what would break if you
> changed any of it.

---

## What is this?

Brahm-Kosh is not a linter. It's not a Copilot wrapper. It doesn't ask
an LLM what your code does.

It's a **static analysis engine + 3D visualizer** built around one idea:

> Code is easier to understand as a graph than as a folder tree.

Point it at a Python, JavaScript, TypeScript, Java, C/C++, C#, Go, Rust,
Dart, PHP, R, SQL, HTML, or CSS project. It returns:

- A hierarchical model: project → modules → files → symbols
- A 0–100 complexity score per file and symbol
- A real cross-file dependency graph (resolved from actual imports, not
  word matching)
- An architectural intelligence report: monoliths, circular dependencies,
  dead files, cross-cutting concerns, refactor split candidates
- Multi-hop impact analysis — *"if you change X, here are all the files
  that transitively break"*
- For Python, symbol-level impact — *"if you rename the class
  `FileModel`, only these 4 files actually break"*
- A live 3D viewer with focus mode, blast-radius coloring, and an
  inline code editor

All offline. All deterministic. Zero LLM calls. Zero non-stdlib
runtime dependencies beyond `click` and `rich` for the CLI output.

---

## Install

```bash
git clone https://github.com/yourname/Brahm-Kosh
cd Brahm-Kosh
pip install -e .
```

Requires Python ≥ 3.9.

---

## Quick start

### Terminal — analyze any repo

```bash
brahm-kosh analyze .                  # current dir, all detected languages
brahm-kosh analyze /path/to/repo
brahm-kosh analyze . --lang python    # restrict to one adapter
brahm-kosh analyze . --top 20         # top 20 hotspots instead of 10
brahm-kosh analyze . --json           # machine-readable output

brahm-kosh diff HEAD~1                # compare architecture against previous commit
```

You get a Rich-formatted report: project stats, full structure tree,
ranked complexity hotspots, and inferred per-file purpose.

### 3D Viewer — explore interactively

```bash
brahm-kosh serve .                    # opens http://127.0.0.1:8080
brahm-kosh serve . --watch            # live-update on file changes
brahm-kosh serve . --watch --no-browser
brahm-kosh serve . --port 8090
```

In the browser:

| Action | Result |
|---|---|
| Click a folder node | Expand / collapse that subtree |
| Click a file node | Focus mode: white core, cyan = files it imports, orange = files that import it |
| Click a row in the Architectural Intelligence panel | Auto-expand the path to that file and focus it |
| Click a `🔗 N` badge next to a symbol | Show every other file that references that specific symbol (Python only) |
| Click background | Clear focus |
| Edit a file in the Code Explorer | Save back via CSRF-protected `/api/save` |

### List all language adapters

```bash
brahm-kosh list-adapters
```

---

## What ships in v1.0

### Core
- 13 language adapters (Python via real AST; others via curated regex)
- Universal code model: `Project → Module → File → Symbol`
- Pluggable adapter registry — adding a new language = one file
- Zero-dependency parsing (only `click` + `rich` for the CLI)

### Analysis layer

| Module | What it does |
|---|---|
| `complexity.py` | Weighted 0–100 score per symbol/file (lines, nesting, branches, calls) |
| `hotspots.py` | Ranks the most complex symbols across the whole project |
| `purpose.py` | Layered heuristic: filename → docstring → symbol names → kind dominance |
| `dependencies.py` | Per-language import extraction, then resolves raw imports to project files |
| `architect.py` | Detects monoliths, circular dependencies, dead files |
| `domains.py` | Tags each file with the *concerns* it touches (DB, UI, network, IO, compute, auth, …); flags files spanning 3+ domains |
| `impact.py` | BFS in both directions: "what breaks if I change this" / "what does this transitively depend on" |
| `symbol_impact.py` | Python-only: AST-based per-symbol usage index. Answers "if I rename `FileModel`, only N files actually break" |
| `refactor.py` | Within-file call graph + union-find. Finds files where the symbols form disjoint clusters and proposes a split |
| `narrator.py` | Deterministic, template-based file summaries (no LLM) |

### 3D Viewer
- WebGL force-graph (3d-force-graph + Three.js, all CDN-loaded)
- Focus mode: directional coloring (cyan out / orange in), edge filtering
- Code Explorer modal: syntax-highlighted source, symbol sidebar,
  inline edit + save, multi-hop impact panel, refactor suggestions
- Live watch mode via Server-Sent Events: file change → 1-second
  poll → server re-analyzes → all open browsers repaint without
  losing focus or expanded folders
- Architectural Intelligence side panel with five sections
  (monolithic / circular / dead / cross-cutting / split candidates)
  — every row clickable

### Security
- Server binds to `127.0.0.1` only
- CSRF token injected per page-load via `<meta name="brahm-token">`
- `/api/save` requires same-origin `Origin` header + token + JSON body +
  bounded payload size + path containment via `Path.resolve()`
- Only files known to the project can be overwritten (no arbitrary writes)

### Testing
58 pytest tests covering adapters, the import resolver, security gates,
SSE, multi-hop impact, domain classification, refactor clustering, and
symbol-level impact. Run with `pytest tests/`.

---

## Architecture

```
brahm_kosh/
├─ models.py              # Universal data model (Project/Module/File/Symbol)
├─ engine.py              # Orchestrator — auto-discovers languages, runs analyzers
├─ cli.py                 # Rich-formatted terminal output
├─ server.py              # ThreadingHTTPServer + SSE + CSRF
├─ watcher.py             # Pure-stdlib polling file watcher
├─ adapters/
│  ├─ registry.py             # Self-registration, extension routing
│  ├─ python_adapter.py       # Real AST
│  ├─ javascript_adapter.py   # Regex (JS/TS/JSX/TSX/MJS/CJS)
│  ├─ c_adapter.py            # Regex (C/C++)
│  ├─ java_adapter.py
│  ├─ csharp_adapter.py
│  ├─ go_adapter.py
│  ├─ rust_adapter.py
│  ├─ dart_adapter.py
│  ├─ php_adapter.py
│  ├─ r_adapter.py
│  ├─ sql_adapter.py
│  ├─ html_adapter.py         # html.parser
│  └─ css_adapter.py
├─ analysis/
│  ├─ complexity.py
│  ├─ hotspots.py
│  ├─ purpose.py
│  ├─ dependencies.py        # raw imports → resolved file paths
│  ├─ domains.py             # imports → concerns
│  ├─ impact.py              # multi-hop BFS
│  ├─ symbol_impact.py       # AST-based name resolution (Python)
│  ├─ refactor.py            # within-file call graph clustering
│  ├─ architect.py
│  └─ narrator.py
└─ frontend/
   ├─ index.html         # Tailwind, 3d-force-graph, focus pill, legend
   ├─ code-explorer.js   # Modal: source view, edit, impact, refactor
   └─ code-explorer.css
```

### Why the universal model matters

Every adapter, no matter the language, produces the same `Project →
Module → File → Symbol` shape. That means complexity scoring, hotspot
ranking, purpose inference, dependency resolution, domain classification,
multi-hop impact, refactor suggestions, and the 3D viewer are all
**language-agnostic**. Adding language N+1 is just another adapter file.

### Why no tree-sitter

The 12 non-Python adapters are deliberately regex-based. Tree-sitter
would catch more edge cases (TypeScript generics with nested `>`, JS
template literals, multi-line C++ signatures) but at the cost of:

- A binary grammar dependency per supported language
- C compilation on install (or pre-built wheels per OS/Python combo)
- Killing the "drop in any environment" simplicity

The current parsers correctly extract symbols on ~85% of real code.
That's the right v1 trade. The day someone runs Brahm-Kosh on a
50k-line TypeScript app and gets garbage, tree-sitter can ship behind
an optional `pip install brahm-kosh[treesitter]` extra.

### Why no LLM

LLMs are non-deterministic, slow, paid, and require an internet
connection. The structural analysis Brahm-Kosh does — finding hotspots,
detecting cycles, computing impact, classifying concerns, suggesting
splits — is the *hard part*, and it's all algorithmic. If an LLM ever
gets bolted on, the right place is at the end of the pipeline ("here
are your top 5 hotspots, here's their dep graph — explain") rather
than as a black-box replacement for the work.

---

## API surface

When `brahm-kosh serve` is running:

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/api/graph` | Flat node/link payload for the 3D viewer |
| GET | `/api/architecture` | Monoliths / circular / dead / cross-cutting / split candidates |
| GET | `/api/file?path=<rel>` | Source + symbols + dependencies + domains + refactor suggestion |
| GET | `/api/impact?path=<rel>` | Multi-hop BFS in both directions, with per-hop breakdown |
| GET | `/api/symbol-impact?file=<rel>&symbol=<name>` | Python-only: every site that references `<symbol>` |
| GET | `/api/events` | Server-Sent Events stream — emits `refresh` when files change in `--watch` mode |
| POST | `/api/save` | Overwrite a known project file (requires `X-Brahm-Token` header) |

---

## Complexity scoring

Each symbol is scored on a 0–100 scale via a weighted formula:

| Factor | Weight | Why it matters |
|---|---|---|
| Line count | 20% | Longer = more to read |
| Nesting depth | 30% | Deeper = harder to follow |
| Branch count | 30% | More branches = more execution paths |
| Call count | 20% | More outbound calls = more coupling |

A file's score is `0.6 × avg_symbol_score + 0.4 × max_symbol_score` —
the average tells you the typical complexity, the max boosts files
that have one nightmare function dragging the rest down.

---

## Roadmap

- **v1.0 (now)** — Multi-language structure, complexity, dependency graph,
  multi-hop impact (file + Python symbol), domain classification,
  refactor clustering, 3D viewer, watch mode.
- **v1.5** — `.brahmkoshignore`, fuzzy file search (`/` shortcut),
  per-language ignore patterns, optional tree-sitter backend.
- **v2.0** — Symbol-level impact across non-Python languages (depends
  on tree-sitter), call-graph-based "find all callers" beyond import
  boundaries, configurable domain table.
- **v3.0 (vision)** — Git churn overlay (which hotspots change most
  often), drift detection across PRs, error-propagation graph from
  exception annotations.

The roadmap is honest: items in v2 / v3 are *not* in the current build.

---

## The user-experience target

A student opens a 200-file repo they've never seen. They run
`brahm-kosh serve . --watch`. The 3D map appears. The hottest file
glows red. The Architectural Intelligence panel says *"server.py mixes
3 concerns: crypto + io + network."* They click it. The Code Explorer
opens. The Multi-hop Impact strip says *"32 files break if you change
this."* They click `FileModel` in the Symbols sidebar. The badge
expands: *"4 references across 4 files."* They edit. They save. The
graph repaints in place.

That's the win — fear replaced with structure.

---

## License

MIT.
