from __future__ import annotations

from pydantic import Field

from suitcode.core.models.graph_types import EdgeKind, EvidenceId, NodeId
from suitcode.core.models.nodes import StrictModel


class Edge(StrictModel):
    kind: EdgeKind
    src: NodeId
    dst: NodeId
    evidence_ids: tuple[EvidenceId, ...] = Field(default_factory=tuple)


EdgeKey = tuple[NodeId, EdgeKind, NodeId]


def edge_key(edge: Edge) -> EdgeKey:
    return (edge.src, edge.kind, edge.dst)
