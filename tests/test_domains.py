"""Domain classification tests."""

from __future__ import annotations

from brahm_kosh.analysis.domains import (
    annotate_project,
    classify_file,
    classify_import,
    cross_cutting_files,
)
from brahm_kosh.models import FileModel, Project


def test_classify_basic_python_imports():
    assert classify_import("sqlalchemy") == "database"
    assert classify_import("requests") == "network"
    assert classify_import("numpy") == "compute"
    assert classify_import("pytest") == "testing"
    assert classify_import("logging") == "logging"


def test_classify_subpath_imports():
    """`requests.adapters` should still classify as network."""
    assert classify_import("requests.adapters") == "network"
    assert classify_import("django.db.models") == "database"
    assert classify_import("os.path") == "io"


def test_classify_javascript_imports():
    assert classify_import("react") == "ui"
    assert classify_import("axios") == "network"
    assert classify_import("mongoose") == "database"
    assert classify_import("jest") == "testing"


def test_classify_unknown_returns_none():
    assert classify_import("brahm_kosh.models") is None
    assert classify_import("my_internal_module") is None
    assert classify_import("") is None


def test_classify_file_aggregates_domains():
    fm = FileModel(
        name="x.py", path="x.py", relative_path="x.py",
        raw_imports=["sqlalchemy", "requests", "logging"],
    )
    domains = classify_file(fm)
    assert domains == {"database", "network", "logging"}


def test_annotate_project_populates_domains_field():
    a = FileModel(
        name="a.py", path="a.py", relative_path="a.py",
        raw_imports=["sqlalchemy", "react", "requests", "bcrypt"],
    )
    b = FileModel(
        name="b.py", path="b.py", relative_path="b.py",
        raw_imports=["numpy"],
    )
    project = Project(name="t", path="/", root_files=[a, b])
    annotate_project(project)
    assert a.domains == {"database", "ui", "network", "auth"}
    assert b.domains == {"compute"}


def test_cross_cutting_files_flags_multi_domain():
    a = FileModel(
        name="a.py", path="a.py", relative_path="a.py",
        raw_imports=["sqlalchemy", "react", "requests", "bcrypt"],  # 4 domains
    )
    b = FileModel(
        name="b.py", path="b.py", relative_path="b.py",
        raw_imports=["numpy"],  # 1 domain
    )
    project = Project(name="t", path="/", root_files=[a, b])
    annotate_project(project)
    flagged = cross_cutting_files(project, threshold=3)
    assert len(flagged) == 1
    assert flagged[0]["file"] == "a.py"
    assert flagged[0]["domain_count"] == 4
    assert "database" in flagged[0]["domains"]
