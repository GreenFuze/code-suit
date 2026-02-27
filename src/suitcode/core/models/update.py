from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from suitcode.core.models.edges import Edge, EdgeKey, edge_key
from suitcode.core.models.graph_types import EvidenceId, NodeId
from suitcode.core.models.nodes import Evidence, GraphNode
from suitcode.core.models.provider_contract import validate_scope
from suitcode.core.models.store.interfaces import GraphStore


@dataclass
class GraphWriter:
    store: GraphStore
    scope: str
    seen_node_ids: set[NodeId] = field(default_factory=set)
    seen_edge_keys: set[EdgeKey] = field(default_factory=set)
    seen_evidence_ids: set[EvidenceId] = field(default_factory=set)

    def upsert_node(self, node: GraphNode) -> None:
        self.store.upsert_node(node, self.scope)
        self.seen_node_ids.add(node.id)

    def upsert_edge(self, edge: Edge) -> None:
        self.store.upsert_edge(edge, self.scope)
        self.seen_edge_keys.add(edge_key(edge))

    def upsert_evidence(self, evidence: Evidence) -> None:
        self.store.upsert_evidence(evidence, self.scope)
        self.seen_evidence_ids.add(evidence.id)


@dataclass
class RefreshSnapshot:
    seen_node_ids: set[NodeId]
    seen_edge_keys: set[EdgeKey]
    seen_evidence_ids: set[EvidenceId]


def run_refresh(
    store: GraphStore,
    scope: str,
    writer_fn: Callable[[GraphWriter], None],
) -> RefreshSnapshot:
    validate_scope(scope)
    with store.transaction():
        writer = GraphWriter(store=store, scope=scope)
        writer_fn(writer)
        store.purge_scope_not_seen(
            scope,
            writer.seen_node_ids,
            writer.seen_edge_keys,
            writer.seen_evidence_ids,
        )
    return RefreshSnapshot(
        seen_node_ids=set(writer.seen_node_ids),
        seen_edge_keys=set(writer.seen_edge_keys),
        seen_evidence_ids=set(writer.seen_evidence_ids),
    )
