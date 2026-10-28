"""`.brahmkoshignore` patterns, including the directory patterns the shipped example uses."""

from __future__ import annotations

from brahm_kosh.adapters.registry import is_ignored, load_ignore_patterns
from brahm_kosh.engine import analyze


def _project_files(root) -> set[str]:
    project, _ = analyze(str(root))
    files = list(project.root_files)
    stack = list(project.modules)
    while stack:
        module = stack.pop()
        files.extend(module.files)
        stack.extend(module.submodules)
    return {f.relative_path for f in files}


def test_directory_pattern_with_trailing_slash_matches_the_directory():
    assert is_ignored("gen", ["gen/"])
    assert is_ignored("pkg/build", ["build/"])
    assert not is_ignored("src", ["gen/"])


def test_file_glob_patterns_still_match():
    assert is_ignored("web/app.min.js", ["*.min.js"])
    assert not is_ignored("web/app.js", ["*.min.js"])


def test_ignored_directory_is_left_out_of_the_analysis(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "gen").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    return 1\n")
    (tmp_path / "gen" / "b.py").write_text("def b():\n    return 2\n")
    (tmp_path / ".brahmkoshignore").write_text("# generated code\ngen/\n")
    load_ignore_patterns.cache_clear()
    assert _project_files(tmp_path) == {"src/a.py"}
