from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any

from suitcode.core.models.edges import Edge
from suitcode.core.models.nodes import Evidence, GraphNode
from suitcode.core.models.subgraph import Subgraph


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def node_payload_json(node: GraphNode) -> str:
    return canonical_json_dumps(node.model_dump(mode="json"))


def edge_payload_json(edge: Edge) -> str:
    return canonical_json_dumps(edge.model_dump(mode="json"))


def evidence_payload_json(evidence: Evidence) -> str:
    return canonical_json_dumps(evidence.model_dump(mode="json"))


def canonical_subgraph_dict(subgraph: Subgraph) -> dict[str, Any]:
    ordered_nodes = OrderedDict(
        (node_id, subgraph.nodes[node_id].model_dump(mode="json"))
        for node_id in sorted(subgraph.nodes.keys())
    )
    ordered_edges = [
        edge.model_dump(mode="json")
        for edge in sorted(subgraph.edges, key=lambda edge: (edge.kind, edge.src, edge.dst))
    ]
    ordered_evidence = OrderedDict(
        (evidence_id, subgraph.evidence[evidence_id].model_dump(mode="json"))
        for evidence_id in sorted(subgraph.evidence.keys())
    )
    return {
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "evidence": ordered_evidence,
    }


def canonical_subgraph_json(subgraph: Subgraph) -> str:
    return canonical_json_dumps(canonical_subgraph_dict(subgraph))
