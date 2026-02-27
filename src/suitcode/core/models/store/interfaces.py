from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from suitcode.core.models.edges import Edge, EdgeKey
from suitcode.core.models.graph_types import EdgeKind, EvidenceId, NodeId, NodeKind
from suitcode.core.models.nodes import Evidence, GraphNode


class GraphStore(Protocol):
    db_path: Path

    def initialize(self) -> None:
        ...

    def close(self) -> None:
        ...

    def begin(self) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...

    def transaction(self) -> AbstractContextManager[None]:
        ...

    def upsert_node(self, node: GraphNode, scope: str) -> None:
        ...

    def delete_node(self, node_id: NodeId) -> None:
        ...

    def upsert_edge(self, edge: Edge, scope: str) -> None:
        ...

    def delete_edge(self, src: NodeId, kind: EdgeKind, dst: NodeId) -> None:
        ...

    def upsert_evidence(self, evidence: Evidence, scope: str) -> None:
        ...

    def get_node(self, node_id: NodeId) -> GraphNode:
        ...

    def get_evidence(self, evidence_id: EvidenceId) -> Evidence:
        ...

    def get_edges_from(self, src: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]:
        ...

    def get_edges_to(self, dst: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]:
        ...

    def list_nodes(self, kind: NodeKind | None, limit: int) -> tuple[GraphNode, ...]:
        ...

    def find_nodes_by_name(self, name: str, *, exact: bool, limit: int) -> tuple[GraphNode, ...]:
        ...

    def purge_scope(self, scope: str) -> None:
        ...

    def purge_scope_not_seen(
        self,
        scope: str,
        seen_node_ids: set[NodeId],
        seen_edge_keys: set[EdgeKey],
        seen_evidence_ids: set[EvidenceId],
    ) -> None:
        ...

    def iter_scope_node_ids(self, scope: str) -> Iterator[NodeId]:
        ...

    def iter_scope_edges(self, scope: str) -> Iterator[EdgeKey]:
        ...

    def iter_scope_evidence_ids(self, scope: str) -> Iterator[EvidenceId]:
        ...
