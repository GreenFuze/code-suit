from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from suitcode.core.models.edges import Edge
from suitcode.core.models.errors import GraphQueryLimitError
from suitcode.core.models.graph_types import ComponentKind, EdgeKind, NodeKind, ProgrammingLanguage
from suitcode.core.models.nodes import Component, Evidence
from suitcode.core.models.workspace_graph import WorkspaceGraph


SCOPE = "provider:test:default"


def _component(node_id: str, name: str) -> Component:
    return Component(
        id=node_id,
        name=name,
        component_kind=ComponentKind.LIBRARY,
        language=ProgrammingLanguage.PYTHON,
    )


def test_workspace_graph_query_deterministic_and_filters() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:
            graph.add_or_update_evidence(Evidence(id="ev:1", message="dep"), SCOPE)
            graph.add_or_update_node(_component("component:a", "a"), SCOPE)
            graph.add_or_update_node(_component("component:b", "b"), SCOPE)
            graph.add_or_update_node(_component("component:c", "c"), SCOPE)

            graph.add_or_update_edge(Edge(kind=EdgeKind.DEPENDS_ON, src="component:a", dst="component:b", evidence_ids=("ev:1",)), SCOPE)
            graph.add_or_update_edge(Edge(kind=EdgeKind.DEPENDS_ON, src="component:b", dst="component:c"), SCOPE)

            sub = graph.query_dependencies("component:a", depth=2, max_nodes=10, max_edges=10)
            assert list(sub.nodes.keys()) == ["component:a", "component:b", "component:c"]
            assert [edge.dst for edge in sub.edges] == ["component:b", "component:c"]
            assert "ev:1" in sub.evidence

            filtered = graph.query_subgraph(
                seed_ids=["component:a"],
                depth=2,
                edge_kinds={EdgeKind.DEPENDS_ON},
                node_kinds={NodeKind.COMPONENT},
                max_nodes=10,
                max_edges=10,
            )
            assert len(filtered.nodes) == 3


def test_workspace_graph_query_limits_are_enforced() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:
            graph.add_or_update_node(_component("component:a", "a"), SCOPE)
            graph.add_or_update_node(_component("component:b", "b"), SCOPE)
            graph.add_or_update_edge(Edge(kind=EdgeKind.DEPENDS_ON, src="component:a", dst="component:b"), SCOPE)

            with pytest.raises(GraphQueryLimitError):
                graph.query_dependencies("component:a", depth=1, max_nodes=1, max_edges=10)
