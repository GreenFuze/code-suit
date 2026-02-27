from __future__ import annotations

from suitcode.core.models.edges import Edge
from suitcode.core.models.graph_types import BuildSystemKind, EdgeKind
from suitcode.core.models.nodes import BuildSystemInfo, Evidence
from suitcode.core.models.serialization import (
    canonical_json_dumps,
    canonical_subgraph_json,
    edge_payload_json,
    node_payload_json,
    sha256_hex,
)
from suitcode.core.models.subgraph import Subgraph


def test_canonical_json_stable() -> None:
    a = canonical_json_dumps({"b": 1, "a": 2})
    b = canonical_json_dumps({"a": 2, "b": 1})
    assert a == b


def test_payload_hash_stable() -> None:
    node = BuildSystemInfo(
        id="build:cmake:debug",
        name="cmake",
        build_system=BuildSystemKind.CMAKE,
        configuration_name="Debug",
    )
    payload = node_payload_json(node)
    assert sha256_hex(payload) == sha256_hex(node_payload_json(node))


def test_canonical_subgraph_json_stable() -> None:
    node = BuildSystemInfo(
        id="build:cmake:debug",
        name="cmake",
        build_system=BuildSystemKind.CMAKE,
        configuration_name="Debug",
    )
    edge = Edge(kind=EdgeKind.RUNS, src=node.id, dst=node.id, evidence_ids=("ev:1",))
    evidence = Evidence(id="ev:1", message="ok")
    subgraph = Subgraph(nodes={node.id: node}, edges=(edge,), evidence={evidence.id: evidence})
    left = canonical_subgraph_json(subgraph)
    right = canonical_subgraph_json(subgraph)
    assert left == right
    assert edge_payload_json(edge)
