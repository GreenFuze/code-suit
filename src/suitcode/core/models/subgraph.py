from __future__ import annotations

from pydantic import Field, model_validator

from suitcode.core.models.edges import Edge
from suitcode.core.models.errors import GraphIntegrityError
from suitcode.core.models.graph_types import EvidenceId, NodeId
from suitcode.core.models.nodes import Evidence, GraphNode, StrictModel


class Subgraph(StrictModel):
    nodes: dict[NodeId, GraphNode] = Field(default_factory=dict)
    edges: tuple[Edge, ...] = Field(default_factory=tuple)
    evidence: dict[EvidenceId, Evidence] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_integrity(self) -> "Subgraph":
        node_ids = list(self.nodes.keys())
        if node_ids != sorted(node_ids):
            raise GraphIntegrityError(
                "nodes must be sorted by node id",
                remediation="Sort node keys lexicographically before building Subgraph.",
            )

        evidence_ids = list(self.evidence.keys())
        if evidence_ids != sorted(evidence_ids):
            raise GraphIntegrityError(
                "evidence must be sorted by evidence id",
                remediation="Sort evidence keys lexicographically before building Subgraph.",
            )

        ordered_edges = sorted(self.edges, key=lambda edge: (edge.kind, edge.src, edge.dst))
        if list(self.edges) != ordered_edges:
            raise GraphIntegrityError(
                "edges must be sorted by (kind, src, dst)",
                remediation="Sort edges deterministically before creating Subgraph.",
            )

        evidence_set = set(self.evidence.keys())
        for node in self.nodes.values():
            missing = set(node.evidence_ids) - evidence_set
            if missing:
                raise GraphIntegrityError(
                    f"node {node.id} references missing evidence: {sorted(missing)}",
                    remediation="Include all referenced evidence in Subgraph.evidence.",
                )

        node_set = set(self.nodes.keys())
        for edge in self.edges:
            if edge.src not in node_set or edge.dst not in node_set:
                raise GraphIntegrityError(
                    f"edge {edge.kind}:{edge.src}->{edge.dst} references missing endpoint",
                    remediation="Ensure both src and dst nodes are included in Subgraph.nodes.",
                )
            missing = set(edge.evidence_ids) - evidence_set
            if missing:
                raise GraphIntegrityError(
                    f"edge {edge.kind}:{edge.src}->{edge.dst} references missing evidence: {sorted(missing)}",
                    remediation="Include all referenced evidence in Subgraph.evidence.",
                )

        return self
