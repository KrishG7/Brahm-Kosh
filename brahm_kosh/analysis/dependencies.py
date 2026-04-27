"""
Dependency Resolver for Brahm-Kosh.

Turns each file's raw import strings (populated by the language adapter
during parsing) into concrete project-relative file paths.

The previous implementation matched any word in a file against a global
symbol table, which produced false edges whenever a common identifier
appeared in a comment, string, or unrelated context. This version only
follows edges the source code explicitly declares via import/include
syntax, so the architect's "monolithic" / "circular" reports reflect
real coupling.
"""

from __future__ import annotations

import os
from typing import Optional

from brahm_kosh.models import FileModel, Project


# Extensions we'll try appending when an import doesn't spell one out.
_TRY_EXTS = [
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".dart", ".php",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx",
    ".html", ".htm", ".css", ".sql", ".r", ".R",
]

# Common package-entry filenames tried when an import resolves to a directory.
_PACKAGE_INDEXES = [
    "__init__.py", "index.js", "index.ts", "index.jsx", "index.tsx",
    "mod.rs", "lib.rs", "main.go",
]


def _try_paths(base: str, files_by_rel: dict[str, FileModel]) -> Optional[str]:
    """Try `base`, then `base.<ext>`, then `base/<index>`. Return a hit or None."""
    if not base:
        return None
    base = base.replace("\\", "/")
    if base in files_by_rel:
        return base
    for ext in _TRY_EXTS:
        cand = base + ext
        if cand in files_by_rel:
            return cand
    for idx in _PACKAGE_INDEXES:
        cand = f"{base}/{idx}" if base else idx
        if cand in files_by_rel:
            return cand
    return None


def _looks_like_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _TRY_EXTS)


def resolve_import(
    raw: str,
    current_rel: str,
    files_by_rel: dict[str, FileModel],
    files_by_basename: dict[str, list[str]],
) -> Optional[str]:
    """
    Resolve one raw import string to a project-relative file path, or None.

    Order:
      1. Relative (`./foo`, `../x/y`) → resolve against current file's dir.
      2. Contains `/` → repo-relative path.
      3. Dotted name (`com.foo.Bar`, `brahm_kosh.models`) → try `a/b/c(.ext)`.
      4. Bare name (`foo`) → look up by basename across the project.
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # 1. Explicit relative path
    if raw.startswith("./") or raw.startswith("../"):
        base_dir = os.path.dirname(current_rel)
        joined = (
            os.path.normpath(os.path.join(base_dir, raw))
            if base_dir else os.path.normpath(raw)
        )
        return _try_paths(joined, files_by_rel)

    # 2. Contains path separator — treat as repo-relative
    if "/" in raw:
        return _try_paths(raw, files_by_rel)

    # 3. Dotted name (but not obvious `name.ext`)
    if "." in raw and not _looks_like_file(raw):
        segments = [s for s in raw.split(".") if s and s != "*"]
        if segments:
            hit = _try_paths("/".join(segments), files_by_rel)
            if hit:
                return hit
            if len(segments) > 1:
                # Java-style `import com.foo.Bar` → try com/foo.java
                hit = _try_paths("/".join(segments[:-1]), files_by_rel)
                if hit:
                    return hit

    # 3b. Looks like a filename (`app.js`)
    if _looks_like_file(raw):
        if raw in files_by_rel:
            return raw
        candidates = files_by_basename.get(raw, [])
        if candidates:
            return min(candidates, key=lambda p: p.count("/"))

    # 4. Bare name
    candidates = files_by_basename.get(raw, [])
    if candidates:
        return min(candidates, key=lambda p: p.count("/"))
    return None


def compute_lexical_dependencies(project: Project) -> None:
    """
    Resolve each file's `raw_imports` into concrete edges.

    Function name retained for backwards compatibility with engine.py; it
    is no longer lexical — it consumes real import declarations emitted
    by each language adapter.
    """
    files: list[FileModel] = project.all_files()

    files_by_rel: dict[str, FileModel] = {fm.relative_path: fm for fm in files}

    files_by_basename: dict[str, list[str]] = {}
    for fm in files:
        stem, _ = os.path.splitext(fm.name)
        files_by_basename.setdefault(fm.name, []).append(fm.relative_path)
        if stem and stem != fm.name:
            files_by_basename.setdefault(stem, []).append(fm.relative_path)

    for fm in files:
        fm.dependencies = []
        seen: set[str] = set()
        for raw in fm.raw_imports:
            target = resolve_import(raw, fm.relative_path, files_by_rel, files_by_basename)
            if target is None or target == fm.relative_path or target in seen:
                continue
            seen.add(target)
            fm.dependencies.append(target)

    for fm in files:
        fm.dependents = []
    for fm in files:
        for dep in fm.dependencies:
            target_fm = files_by_rel.get(dep)
            if target_fm and fm.relative_path not in target_fm.dependents:
                target_fm.dependents.append(fm.relative_path)
