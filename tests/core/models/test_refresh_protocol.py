from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from suitcode.core.models.edges import Edge
from suitcode.core.models.graph_types import ComponentKind, EdgeKind, ProgrammingLanguage
from suitcode.core.models.nodes import Component
from suitcode.core.provenance_builders import manifest_provenance
from suitcode.core.models.workspace_graph import WorkspaceGraph


def _component(node_id: str, name: str) -> Component:
    return Component(
        id=node_id,
        name=name,
        component_kind=ComponentKind.LIBRARY,
        language=ProgrammingLanguage.PYTHON,
        provenance=(
            manifest_provenance(
                evidence_summary="derived from test component fixture",
                evidence_paths=("pyproject.toml",),
            ),
        ),
    )


def test_refresh_is_atomic_on_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:

            def failing_writer(writer):
                writer.upsert_node(_component("component:a", "a"))
                raise RuntimeError("boom")

            with pytest.raises(RuntimeError):
                graph.refresh("provider:test:default", failing_writer)

            assert graph.store.list_nodes(None, 10) == tuple()


def test_refresh_purges_only_stale_items_in_scope() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:
            graph.refresh(
                "provider:test:default",
                lambda w: w.upsert_node(_component("component:a", "a")),
            )
            graph.refresh(
                "provider:other:default",
                lambda w: w.upsert_node(_component("component:b", "b")),
            )

            graph.refresh(
                "provider:test:default",
                lambda w: w.upsert_node(_component("component:c", "c")),
            )

            names = [node.name for node in graph.store.list_nodes(None, 10)]
            assert names == ["b", "c"]


def test_refresh_purges_stale_edges() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:

            def seed(writer):
                writer.upsert_node(_component("component:a", "a"))
                writer.upsert_node(_component("component:b", "b"))
                writer.upsert_edge(Edge(kind=EdgeKind.DEPENDS_ON, src="component:a", dst="component:b"))

            graph.refresh("provider:test:default", seed)

            def rewrite_without_edge(writer):
                writer.upsert_node(_component("component:a", "a"))
                writer.upsert_node(_component("component:b", "b"))

            graph.refresh("provider:test:default", rewrite_without_edge)
            assert graph.store.get_edges_from("component:a", None, 10) == tuple()
