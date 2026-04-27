"""Unit tests for the import resolver."""

from __future__ import annotations

from brahm_kosh.analysis.dependencies import resolve_import


def _index(*paths: str):
    """Build the two dicts resolve_import wants. Values don't matter — keys do."""
    files_by_rel = {p: object() for p in paths}
    files_by_basename: dict[str, list[str]] = {}
    for p in paths:
        import os
        name = os.path.basename(p)
        stem, _ = os.path.splitext(name)
        files_by_basename.setdefault(name, []).append(p)
        if stem and stem != name:
            files_by_basename.setdefault(stem, []).append(p)
    return files_by_rel, files_by_basename


def test_relative_import_resolves_to_sibling():
    by_rel, by_base = _index("src/a.py", "src/b.py")
    assert resolve_import("./b", "src/a.py", by_rel, by_base) == "src/b.py"


def test_parent_relative_import():
    by_rel, by_base = _index("src/a.py", "lib/helper.py")
    assert resolve_import("../lib/helper", "src/a.py", by_rel, by_base) == "lib/helper.py"


def test_dotted_python_style():
    by_rel, by_base = _index("foo/bar.py", "foo/__init__.py")
    assert resolve_import("foo.bar", "entry.py", by_rel, by_base) == "foo/bar.py"


def test_dotted_java_style_drops_last_segment():
    # `import com.foo.Bar;` where com/foo.java is the actual file
    by_rel, by_base = _index("com/foo.java")
    assert resolve_import("com.foo.Bar", "App.java", by_rel, by_base) == "com/foo.java"


def test_bare_name_finds_by_basename():
    by_rel, by_base = _index("deep/nested/shared.py")
    assert resolve_import("shared", "other.py", by_rel, by_base) == "deep/nested/shared.py"


def test_external_imports_do_not_resolve():
    by_rel, by_base = _index("src/a.py")
    assert resolve_import("numpy", "src/a.py", by_rel, by_base) is None
    assert resolve_import("react", "src/a.js", by_rel, by_base) is None


def test_explicit_extension_matches():
    by_rel, by_base = _index("assets/app.js")
    assert resolve_import("./app.js", "index.html", by_rel, by_base) == "assets/app.js" or \
           resolve_import("assets/app.js", "index.html", by_rel, by_base) == "assets/app.js"


def test_repo_relative_path():
    by_rel, by_base = _index("include/header.h", "src/main.c")
    assert resolve_import("include/header.h", "src/main.c", by_rel, by_base) == "include/header.h"


def test_shallowest_match_wins():
    by_rel, by_base = _index("utils.py", "deep/nested/utils.py")
    assert resolve_import("utils", "x.py", by_rel, by_base) == "utils.py"


def test_self_import_is_not_a_dep():
    # Resolver can resolve to self; the caller (compute_lexical_dependencies)
    # filters it. Here we just check resolve_import doesn't lie about it.
    by_rel, by_base = _index("a.py")
    resolved = resolve_import("a", "a.py", by_rel, by_base)
    assert resolved == "a.py"


def test_empty_or_whitespace_import_returns_none():
    assert resolve_import("", "a.py", {}, {}) is None
    assert resolve_import("   ", "a.py", {}, {}) is None
