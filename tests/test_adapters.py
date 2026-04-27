"""
Smoke tests for each language adapter.

Runs the adapter against a fixture tree and asserts stable invariants:
  - the adapter ran (FileModel exists with correct language)
  - symbols were extracted (non-zero count where we know code has them)
  - imports were extracted where the fixture has them
"""

from __future__ import annotations

import os
import pytest

from brahm_kosh.engine import analyze


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="module")
def fixture_project():
    project, _ = analyze(FIXTURES, top_n=5)
    return project


def _files_by_language(project, lang: str):
    return [f for f in project.all_files() if f.language == lang]


def test_project_contains_multiple_languages(fixture_project):
    langs = set(fm.language for fm in fixture_project.all_files())
    # We ship fixtures for at least these five
    assert {"Python", "JavaScript/TypeScript", "C/C++", "HTML", "CSS"}.issubset(langs)


def test_python_adapter_extracts_classes_and_imports(fixture_project):
    py_files = _files_by_language(fixture_project, "Python")
    assert py_files, "no Python files picked up"

    app = next(f for f in py_files if f.name == "app.py")
    assert any(s.name == "App" for s in app.symbols)
    assert any(s.name == "main" for s in app.symbols)
    # Imports include os, sys, and the sibling `shared` module
    assert "shared" in app.raw_imports
    # App.greet exists as a method with at least one branch (if who)
    app_cls = next(s for s in app.symbols if s.name == "App")
    assert any(m.name == "greet" for m in app_cls.children)


def test_javascript_adapter_extracts_functions(fixture_project):
    js_files = _files_by_language(fixture_project, "JavaScript/TypeScript")
    assert js_files
    app = next(f for f in js_files if f.name == "app.js")
    names = {s.name for s in app.symbols}
    assert "fetchUser" in names
    assert "UserService" in names


def test_c_adapter_extracts_functions(fixture_project):
    c_files = _files_by_language(fixture_project, "C/C++")
    assert c_files
    main_c = next(f for f in c_files if f.name == "main.c")
    assert main_c.symbols, "expected at least one function in main.c"


def test_html_adapter_runs(fixture_project):
    html_files = _files_by_language(fixture_project, "HTML")
    assert html_files


def test_css_adapter_runs(fixture_project):
    css_files = _files_by_language(fixture_project, "CSS")
    assert css_files


def test_every_file_has_complexity_score(fixture_project):
    for fm in fixture_project.all_files():
        assert 0.0 <= fm.complexity <= 100.0


def test_every_file_has_purpose(fixture_project):
    for fm in fixture_project.all_files():
        assert fm.purpose, f"missing purpose on {fm.relative_path}"
