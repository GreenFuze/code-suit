from __future__ import annotations

import tempfile
from pathlib import Path

from suitcode.core.models.edges import Edge
from suitcode.core.models.graph_types import EdgeKind, NodeKind
from suitcode.core.models.ids import make_entity_id, make_file_id, normalize_repository_relative_path
from suitcode.core.models.nodes import EntityInfo, FileInfo
from suitcode.core.models.workspace_graph import WorkspaceGraph


SCOPE = "provider:parser:default"


def test_file_entity_id_helpers() -> None:
    assert normalize_repository_relative_path("src\\pkg\\a.py") == "src/pkg/a.py"
    assert make_file_id("src/pkg/a.py") == "file:src/pkg/a.py"
    assert make_entity_id("src/pkg/a.py", "function", "main", 1, 3) == "entity:src/pkg/a.py:function:main:1-3"


def test_file_contains_entity_edge_query() -> None:
    with tempfile.TemporaryDirectory() as td:
        with WorkspaceGraph(Path(td)) as graph:
            file_id = make_file_id("src/pkg/a.py")
            entity_id = make_entity_id("src/pkg/a.py", "function", "main", 1, 3)

            graph.add_or_update_node(
                FileInfo(
                    id=file_id,
                    name="src/pkg/a.py",
                    repository_rel_path="src/pkg/a.py",
                    owner_id="component:demo",
                ),
                SCOPE,
            )
            graph.add_or_update_node(
                EntityInfo(
                    id=entity_id,
                    name="main",
                    repository_rel_path="src/pkg/a.py",
                    entity_kind="function",
                    line_start=1,
                    line_end=3,
                ),
                SCOPE,
            )
            graph.add_or_update_edge(
                Edge(kind=EdgeKind.FILE_CONTAINS_ENTITY, src=file_id, dst=entity_id),
                SCOPE,
            )

            sub = graph.query_subgraph(
                seed_ids=[file_id],
                depth=1,
                edge_kinds={EdgeKind.FILE_CONTAINS_ENTITY},
                node_kinds={NodeKind.FILE, NodeKind.ENTITY},
                max_nodes=10,
                max_edges=10,
            )
            assert list(sub.nodes.keys()) == [entity_id, file_id]
            assert sub.edges[0].kind == EdgeKind.FILE_CONTAINS_ENTITY
