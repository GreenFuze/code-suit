from __future__ import annotations

import pytest

from suitcode.core.models.edges import Edge
from suitcode.core.models.errors import GraphIntegrityError
from suitcode.core.models.graph_types import EdgeKind
from suitcode.core.models.nodes import Evidence, FileInfo
from suitcode.core.models.subgraph import Subgraph


def _node(node_id: str) -> FileInfo:
    return FileInfo(
        id=node_id,
        name=node_id.split(":", 1)[1],
        repository_rel_path=node_id.split(":", 1)[1],
        owner_id="component:test",
    )


def test_subgraph_integrity_happy_path() -> None:
    nodes = {
        "file:a.py": _node("file:a.py"),
        "file:b.py": _node("file:b.py"),
    }
    edges = (
        Edge(kind=EdgeKind.DEPENDS_ON, src="file:a.py", dst="file:b.py", evidence_ids=("ev:1",)),
    )
    evidence = {"ev:1": Evidence(id="ev:1", message="ok")}

    graph = Subgraph(nodes=nodes, edges=edges, evidence=evidence)
    assert graph.nodes["file:a.py"].name == "a.py"


def test_subgraph_requires_sorted_nodes() -> None:
    with pytest.raises(GraphIntegrityError):
        Subgraph(
            nodes={"file:b.py": _node("file:b.py"), "file:a.py": _node("file:a.py")},
            edges=(),
            evidence={},
        )


def test_subgraph_requires_edge_endpoints() -> None:
    with pytest.raises(GraphIntegrityError):
        Subgraph(
            nodes={"file:a.py": _node("file:a.py")},
            edges=(Edge(kind=EdgeKind.DEPENDS_ON, src="file:a.py", dst="file:b.py"),),
            evidence={},
        )
