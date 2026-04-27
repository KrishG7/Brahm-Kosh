"""Refactor suggestion engine tests."""

from __future__ import annotations

from brahm_kosh.analysis.refactor import suggest_splits, project_split_candidates
from brahm_kosh.models import FileModel, Project, Symbol, SymbolKind


def _sym(name, calls=None, line_start=1, line_end=10):
    return Symbol(
        name=name,
        kind=SymbolKind.FUNCTION,
        line_start=line_start,
        line_end=line_end,
        calls=calls or [],
    )


def test_no_split_when_all_symbols_call_each_other():
    fm = FileModel(
        name="cohesive.py", path="cohesive.py", relative_path="cohesive.py",
        symbols=[
            _sym("a", calls=["b"]),
            _sym("b", calls=["c"]),
            _sym("c", calls=["a"]),
            _sym("d", calls=["a"]),
        ],
    )
    assert suggest_splits(fm) == []


def test_split_suggested_for_two_disjoint_groups():
    """Group {a,b,c} all call each other; group {x,y,z} all call each other.
    No edges between groups. Should suggest a 2-way split."""
    fm = FileModel(
        name="mixed.py", path="mixed.py", relative_path="mixed.py",
        symbols=[
            _sym("parse_a",  calls=["parse_b"], line_start=1,  line_end=10),
            _sym("parse_b",  calls=["parse_c"], line_start=11, line_end=20),
            _sym("parse_c",  calls=["parse_a"], line_start=21, line_end=30),
            _sym("render_x", calls=["render_y"], line_start=31, line_end=40),
            _sym("render_y", calls=["render_z"], line_start=41, line_end=50),
            _sym("render_z", calls=["render_x"], line_start=51, line_end=60),
        ],
    )
    clusters = suggest_splits(fm)
    assert len(clusters) == 2
    # Each cluster has 3 members
    sizes = sorted(len(c.members) for c in clusters)
    assert sizes == [3, 3]
    # The verb-based purpose hint catches "parse" and "render"
    purposes = sorted(c.suggested_purpose for c in clusters)
    assert purposes == ["parsing", "rendering"]


def test_no_split_below_min_symbols_threshold():
    fm = FileModel(
        name="tiny.py", path="tiny.py", relative_path="tiny.py",
        symbols=[_sym("a"), _sym("b")],  # only 2, below default min=4
    )
    assert suggest_splits(fm) == []


def test_singleton_components_dropped():
    """If we have one big group + several lonely singletons, only count
    the multi-symbol group(s) — splitting off lone helpers isn't useful."""
    fm = FileModel(
        name="m.py", path="m.py", relative_path="m.py",
        symbols=[
            _sym("a", calls=["b"]),
            _sym("b", calls=["a"]),
            _sym("loner1"),
            _sym("loner2"),
            _sym("loner3"),
        ],
    )
    # one component of size 2, three of size 1 → only one multi → no split
    assert suggest_splits(fm) == []


def test_project_split_candidates_includes_files_with_groups():
    fm = FileModel(
        name="mixed.py", path="mixed.py", relative_path="mixed.py",
        complexity=70.0,
        symbols=[
            _sym("parse_a",  calls=["parse_b"], line_start=1,  line_end=10),
            _sym("parse_b",  calls=["parse_a"], line_start=11, line_end=20),
            _sym("save_x",   calls=["save_y"],  line_start=21, line_end=30),
            _sym("save_y",   calls=["save_x"],  line_start=31, line_end=40),
        ],
    )
    project = Project(name="t", path="/", root_files=[fm])
    out = project_split_candidates(project)
    assert len(out) == 1
    assert out[0]["file"] == "mixed.py"
    assert len(out[0]["clusters"]) == 2


def test_cluster_to_dict_includes_line_range():
    fm = FileModel(
        name="m.py", path="m.py", relative_path="m.py",
        symbols=[
            _sym("a", calls=["b"], line_start=1,  line_end=10),
            _sym("b", calls=["a"], line_start=11, line_end=20),
            _sym("x", calls=["y"], line_start=50, line_end=60),
            _sym("y", calls=["x"], line_start=61, line_end=70),
        ],
    )
    clusters = suggest_splits(fm)
    assert len(clusters) == 2
    for c in clusters:
        d = c.to_dict()
        assert "members" in d
        assert "line_start" in d and "line_end" in d
        assert d["line_end"] >= d["line_start"]
        assert d["size"] == len(d["members"])
