from __future__ import annotations

from collections import deque

from suitcode.core.models.edges import Edge
from suitcode.core.models.errors import GraphNotFoundError, GraphQueryLimitError
from suitcode.core.models.graph_types import EdgeKind, NodeId, NodeKind
from suitcode.core.models.nodes import Evidence, GraphNode
from suitcode.core.models.store.interfaces import GraphStore
from suitcode.core.models.subgraph import Subgraph


def _raise_if_exceeds(max_value: int, observed: int, what: str, db_path) -> None:
    if observed > max_value:
        raise GraphQueryLimitError(
            f"query exceeded {what} limit: {observed}>{max_value}",
            remediation="Increase max limits or narrow query parameters.",
            db_path=db_path,
        )


def _sorted_subgraph(
    nodes: dict[NodeId, GraphNode],
    edges: set[tuple[EdgeKind, NodeId, NodeId]],
    edge_map: dict[tuple[EdgeKind, NodeId, NodeId], Edge],
    evidence: dict[str, Evidence],
) -> Subgraph:
    ordered_nodes = {node_id: nodes[node_id] for node_id in sorted(nodes.keys())}
    ordered_edges = tuple(edge_map[key] for key in sorted(edges, key=lambda key: (key[0], key[1], key[2])))
    ordered_evidence = {evidence_id: evidence[evidence_id] for evidence_id in sorted(evidence.keys())}
    return Subgraph(nodes=ordered_nodes, edges=ordered_edges, evidence=ordered_evidence)


def query_subgraph_bfs(
    store: GraphStore,
    *,
    seed_ids: list[NodeId],
    depth: int,
    edge_kinds: set[EdgeKind] | None,
    node_kinds: set[NodeKind] | None,
    max_nodes: int,
    max_edges: int,
    direction: str,
) -> Subgraph:
    if depth < 0:
        raise ValueError("depth must be >= 0")
    if max_nodes <= 0 or max_edges <= 0:
        raise ValueError("max_nodes and max_edges must be > 0")

    distance: dict[NodeId, int] = {}
    nodes: dict[NodeId, GraphNode] = {}
    edge_keys: set[tuple[EdgeKind, NodeId, NodeId]] = set()
    edge_map: dict[tuple[EdgeKind, NodeId, NodeId], Edge] = {}
    evidence: dict[str, Evidence] = {}

    for seed_id in sorted(seed_ids):
        node = store.get_node(seed_id)
        if node_kinds and node.kind not in node_kinds:
            continue
        if seed_id not in distance:
            distance[seed_id] = 0
            nodes[seed_id] = node

    _raise_if_exceeds(max_nodes, len(nodes), "node", store.db_path)
    queue = deque(sorted(distance.keys()))

    while queue:
        current = queue.popleft()
        current_depth = distance[current]
        if current_depth >= depth:
            continue

        outgoing = ()
        incoming = ()
        if direction in {"out", "both"}:
            outgoing = store.get_edges_from(current, edge_kinds, max_edges + 1)
        if direction in {"in", "both"}:
            incoming = store.get_edges_to(current, edge_kinds, max_edges + 1)

        all_edges = sorted(
            tuple(outgoing) + tuple(incoming),
            key=lambda edge: (edge.kind, edge.src, edge.dst),
        )

        for edge in all_edges:
            key = (edge.kind, edge.src, edge.dst)
            if key not in edge_keys:
                edge_keys.add(key)
                edge_map[key] = edge
                _raise_if_exceeds(max_edges, len(edge_keys), "edge", store.db_path)

            next_node_id = edge.dst if edge.src == current else edge.src
            if next_node_id in distance:
                continue

            try:
                next_node = store.get_node(next_node_id)
            except GraphNotFoundError:
                continue

            if node_kinds and next_node.kind not in node_kinds:
                continue

            distance[next_node_id] = current_depth + 1
            nodes[next_node_id] = next_node
            _raise_if_exceeds(max_nodes, len(nodes), "node", store.db_path)
            queue.append(next_node_id)

    for node in nodes.values():
        for evidence_id in node.evidence_ids:
            if evidence_id not in evidence:
                evidence[evidence_id] = store.get_evidence(evidence_id)

    for edge in edge_map.values():
        for evidence_id in edge.evidence_ids:
            if evidence_id not in evidence:
                evidence[evidence_id] = store.get_evidence(evidence_id)

    return _sorted_subgraph(nodes, edge_keys, edge_map, evidence)
