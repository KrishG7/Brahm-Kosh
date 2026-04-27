"""Multi-hop impact analysis tests."""

from __future__ import annotations

from brahm_kosh.analysis.impact import (
    ImpactSet,
    compute_downstream_impact,
    compute_full_impact,
    compute_upstream_impact,
    _bfs,
)
from brahm_kosh.models import FileModel, Project


def _project_with_chain():
    """A → B → C → D (linear). a depends on b, etc."""
    a = FileModel(name="a.py", path="a.py", relative_path="a.py", dependencies=["b.py"], dependents=[])
    b = FileModel(name="b.py", path="b.py", relative_path="b.py", dependencies=["c.py"], dependents=["a.py"])
    c = FileModel(name="c.py", path="c.py", relative_path="c.py", dependencies=["d.py"], dependents=["b.py"])
    d = FileModel(name="d.py", path="d.py", relative_path="d.py", dependencies=[],          dependents=["c.py"])
    p = Project(name="t", path="/", root_files=[a, b, c, d])
    return p


def test_bfs_linear_chain():
    edges = {"a": ["b"], "b": ["c"], "c": ["d"], "d": []}
    result = _bfs("a", edges)
    assert result == {1: ["b"], 2: ["c"], 3: ["d"]}


def test_bfs_respects_max_depth():
    edges = {"a": ["b"], "b": ["c"], "c": ["d"], "d": []}
    result = _bfs("a", edges, max_depth=2)
    assert 3 not in result
    assert result[1] == ["b"] and result[2] == ["c"]


def test_bfs_handles_cycles_without_infinite_loop():
    edges = {"a": ["b"], "b": ["a", "c"], "c": ["a"]}
    result = _bfs("a", edges)
    # Should reach b and c, each exactly once
    seen = set()
    for nodes in result.values():
        seen.update(nodes)
    assert seen == {"b", "c"}


def test_downstream_impact_walks_full_chain():
    p = _project_with_chain()
    impact = compute_downstream_impact("a.py", p)
    assert impact.direct == ["b.py"]
    assert "c.py" in impact.indirect
    assert "d.py" in impact.indirect
    assert impact.total_count == 3
    assert impact.max_depth == 3


def test_upstream_impact_walks_reverse_chain():
    """Changing d.py breaks c, b, and a (transitively)."""
    p = _project_with_chain()
    impact = compute_upstream_impact("d.py", p)
    assert impact.direct == ["c.py"]
    assert {"b.py", "a.py"}.issubset(set(impact.indirect))
    assert impact.total_count == 3


def test_upstream_for_leaf_with_no_dependents_is_empty():
    p = _project_with_chain()
    impact = compute_upstream_impact("a.py", p)
    assert impact.total_count == 0


def test_compute_full_impact_returns_both_directions():
    p = _project_with_chain()
    payload = compute_full_impact("c.py", p)
    assert payload["path"] == "c.py"
    assert payload["upstream"]["total_count"] == 2  # b, a
    assert payload["downstream"]["total_count"] == 1  # d


def test_impact_set_to_dict_shape():
    s = ImpactSet(
        direct=["b"], indirect=["c"], by_hop={1: ["b"], 2: ["c"]},
        total=["b", "c"],
    )
    d = s.to_dict()
    assert d["direct"] == ["b"]
    assert d["indirect"] == ["c"]
    assert d["total_count"] == 2
    assert d["max_depth"] == 2
    assert d["by_hop"] == {"1": ["b"], "2": ["c"]}
