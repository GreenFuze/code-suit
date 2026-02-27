from __future__ import annotations

from pathlib import Path
from typing import Callable

from suitcode.core.models.edges import Edge
from suitcode.core.models.errors import GraphIntegrityError
from suitcode.core.models.graph_types import EdgeKind, NodeId, NodeKind
from suitcode.core.models.nodes import Evidence, GraphNode
from suitcode.core.models.provider_contract import validate_scope
from suitcode.core.models.queries import query_subgraph_bfs
from suitcode.core.models.store.interfaces import GraphStore
from suitcode.core.models.store.sqlite_store import SQLiteGraphStore
from suitcode.core.models.subgraph import Subgraph
from suitcode.core.models.update import run_refresh


class WorkspaceGraph:
    def __init__(self, repository_root: Path, store: GraphStore | None = None) -> None:
        self.repository_root = repository_root.expanduser().resolve()
        self.db_path = self.repository_root / ".suit" / "db" / "workspace.sqlite3"
        if store is None:
            store = SQLiteGraphStore(self.db_path, self.repository_root)
        self.store = store
        self.store.initialize()

    def add_or_update_node(self, node: GraphNode, scope: str) -> None:
        validate_scope(scope)
        self.store.upsert_node(node, scope)
        self.store.commit()

    def add_or_update_edge(self, edge: Edge, scope: str) -> None:
        validate_scope(scope)
        self.store.upsert_edge(edge, scope)
        self.store.commit()

    def add_or_update_evidence(self, evidence: Evidence, scope: str) -> None:
        validate_scope(scope)
        self.store.upsert_evidence(evidence, scope)
        self.store.commit()

    def remove_node(self, node_id: NodeId) -> None:
        self.store.delete_node(node_id)
        self.store.commit()

    def remove_edge(self, src: NodeId, kind: EdgeKind, dst: NodeId) -> None:
        self.store.delete_edge(src, kind, dst)
        self.store.commit()

    def get_node(self, node_id: NodeId, expected_kind: NodeKind | None = None) -> GraphNode:
        node = self.store.get_node(node_id)
        if expected_kind is not None and node.kind != expected_kind:
            raise GraphIntegrityError(
                f"node {node_id} has kind {node.kind}, expected {expected_kind}",
                remediation="Read without expected_kind or pass the correct NodeKind.",
                db_path=self.db_path,
            )
        return node

    def query_subgraph(
        self,
        seed_ids: list[NodeId],
        depth: int,
        edge_kinds: set[EdgeKind] | None,
        node_kinds: set[NodeKind] | None,
        max_nodes: int,
        max_edges: int,
    ) -> Subgraph:
        return query_subgraph_bfs(
            self.store,
            seed_ids=seed_ids,
            depth=depth,
            edge_kinds=edge_kinds,
            node_kinds=node_kinds,
            max_nodes=max_nodes,
            max_edges=max_edges,
            direction="both",
        )

    def query_components(self, max_nodes: int) -> Subgraph:
        nodes = self.store.list_nodes(NodeKind.COMPONENT, max_nodes)
        return self.query_subgraph(
            seed_ids=[node.id for node in nodes],
            depth=0,
            edge_kinds=None,
            node_kinds=None,
            max_nodes=max_nodes,
            max_edges=max(max_nodes, 1),
        )

    def query_component_by_name(self, name: str, max_nodes: int) -> Subgraph:
        nodes = [
            node
            for node in self.store.find_nodes_by_name(name, exact=True, limit=max_nodes)
            if node.kind == NodeKind.COMPONENT
        ]
        return self.query_subgraph(
            seed_ids=[node.id for node in nodes],
            depth=0,
            edge_kinds=None,
            node_kinds={NodeKind.COMPONENT},
            max_nodes=max_nodes,
            max_edges=max(max_nodes, 1),
        )

    def query_dependents(self, node_id: NodeId, depth: int, max_nodes: int, max_edges: int) -> Subgraph:
        return query_subgraph_bfs(
            self.store,
            seed_ids=[node_id],
            depth=depth,
            edge_kinds={EdgeKind.DEPENDS_ON},
            node_kinds=None,
            max_nodes=max_nodes,
            max_edges=max_edges,
            direction="in",
        )

    def query_dependencies(self, node_id: NodeId, depth: int, max_nodes: int, max_edges: int) -> Subgraph:
        return query_subgraph_bfs(
            self.store,
            seed_ids=[node_id],
            depth=depth,
            edge_kinds={EdgeKind.DEPENDS_ON},
            node_kinds=None,
            max_nodes=max_nodes,
            max_edges=max_edges,
            direction="out",
        )

    def refresh(self, scope: str, writer_fn: Callable) -> None:
        run_refresh(self.store, scope, writer_fn)

    def list_components(self, max_nodes: int = 100) -> Subgraph:
        return self.query_components(max_nodes=max_nodes)

    def get_component(self, node_id: NodeId, depth: int = 1, max_nodes: int = 100, max_edges: int = 100) -> Subgraph:
        return self.query_subgraph(
            seed_ids=[node_id],
            depth=depth,
            edge_kinds=None,
            node_kinds=None,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def get_component_dependencies(self, node_id: NodeId, depth: int = 1, max_nodes: int = 100, max_edges: int = 100) -> Subgraph:
        return self.query_dependencies(node_id=node_id, depth=depth, max_nodes=max_nodes, max_edges=max_edges)

    def get_component_dependents(self, node_id: NodeId, depth: int = 1, max_nodes: int = 100, max_edges: int = 100) -> Subgraph:
        return self.query_dependents(node_id=node_id, depth=depth, max_nodes=max_nodes, max_edges=max_edges)

    def find_by_name(self, name: str, *, exact: bool = False, max_nodes: int = 50, max_edges: int = 100) -> Subgraph:
        nodes = self.store.find_nodes_by_name(name, exact=exact, limit=max_nodes)
        return self.query_subgraph(
            seed_ids=[node.id for node in nodes],
            depth=0,
            edge_kinds=None,
            node_kinds=None,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "WorkspaceGraph":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
