"""Symbol-level impact analysis tests.

Uses real (tiny) Python files written into a tmpdir so the AST walker
hits the same code paths it does on a live project.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from brahm_kosh.engine import analyze
from brahm_kosh.analysis.symbol_impact import (
    build_symbol_usage_index,
    compute_symbol_impact,
    per_file_symbol_counts,
)


@pytest.fixture
def mini_project(tmp_path: Path):
    """A 4-file Python project with cross-file symbol references."""
    (tmp_path / "models.py").write_text(textwrap.dedent("""
        class FileModel:
            pass

        class Project:
            pass

        def helper():
            return 42
    """).strip())

    (tmp_path / "engine.py").write_text(textwrap.dedent("""
        from models import FileModel, helper

        def run():
            fm = FileModel()
            return helper()
    """).strip())

    (tmp_path / "cli.py").write_text(textwrap.dedent("""
        import models

        def main():
            return models.FileModel()
    """).strip())

    (tmp_path / "unrelated.py").write_text(textwrap.dedent("""
        def standalone():
            return 1
    """).strip())

    project, _ = analyze(str(tmp_path))
    return project


def test_index_records_from_import_usages(mini_project):
    index = build_symbol_usage_index(mini_project)
    # `engine.py` references FileModel via `from models import FileModel`
    fm_uses = index.get("models.py:FileModel", [])
    assert any(u.file == "engine.py" for u in fm_uses), (
        f"engine.py should appear; got {fm_uses}"
    )


def test_index_records_module_attribute_usages(mini_project):
    index = build_symbol_usage_index(mini_project)
    # `cli.py` references `models.FileModel` via `import models`
    fm_uses = index.get("models.py:FileModel", [])
    assert any(u.file == "cli.py" for u in fm_uses), (
        f"cli.py should appear via Attribute access; got {fm_uses}"
    )


def test_index_excludes_self_references(mini_project):
    index = build_symbol_usage_index(mini_project)
    fm_uses = index.get("models.py:FileModel", [])
    # FileModel is *defined* in models.py — usages must NOT include models.py
    assert not any(u.file == "models.py" for u in fm_uses)


def test_unused_symbol_has_no_usages(mini_project):
    index = build_symbol_usage_index(mini_project)
    # `Project` is defined but never imported anywhere
    assert "models.py:Project" not in index or not index["models.py:Project"]


def test_unrelated_file_does_not_appear_as_user(mini_project):
    index = build_symbol_usage_index(mini_project)
    fm_uses = index.get("models.py:FileModel", [])
    assert not any(u.file == "unrelated.py" for u in fm_uses)


def test_compute_symbol_impact_returns_full_payload(mini_project):
    index = build_symbol_usage_index(mini_project)
    payload = compute_symbol_impact("models.py", "FileModel", index)
    assert payload["symbol"] == "FileModel"
    assert payload["defined_in"] == "models.py"
    assert payload["file_count"] == 2  # engine.py + cli.py
    assert set(payload["files"]) == {"engine.py", "cli.py"}
    assert payload["usage_count"] >= 2


def test_compute_symbol_impact_for_unused_symbol(mini_project):
    index = build_symbol_usage_index(mini_project)
    payload = compute_symbol_impact("models.py", "Project", index)
    assert payload["usage_count"] == 0
    assert payload["file_count"] == 0
    assert payload["files"] == []


def test_per_file_symbol_counts(mini_project):
    index = build_symbol_usage_index(mini_project)
    models_fm = next(f for f in mini_project.all_files() if f.name == "models.py")
    counts = per_file_symbol_counts("models.py", models_fm.symbols, index)
    # FileModel used in 2 files, helper used in 1, Project used in 0
    assert counts.get("FileModel") == 2
    assert counts.get("helper") == 1
    assert counts.get("Project") == 0
