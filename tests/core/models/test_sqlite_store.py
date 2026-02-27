from __future__ import annotations

import tempfile
from pathlib import Path

from suitcode.core.models.edges import Edge
from suitcode.core.models.graph_types import BuildSystemKind, EdgeKind, NodeKind
from suitcode.core.models.nodes import BuildSystemInfo, Evidence
from suitcode.core.models.store.sqlite_store import SQLiteGraphStore


def test_sqlite_store_roundtrip_and_indexes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db_path = root / ".suit" / "db" / "workspace.sqlite3"
        store = SQLiteGraphStore(db_path, root)
        store.initialize()

        node = BuildSystemInfo(
            id="build:cmake:debug",
            name="cmake-debug",
            build_system=BuildSystemKind.CMAKE,
            configuration_name="Debug",
        )
        evidence = Evidence(id="ev:1", message="from tool")
        edge = Edge(kind=EdgeKind.RUNS, src=node.id, dst=node.id, evidence_ids=("ev:1",))

        store.begin()
        store.upsert_node(node, "provider:cmake:default")
        store.upsert_evidence(evidence, "provider:cmake:default")
        store.upsert_edge(edge, "provider:cmake:default")
        store.commit()

        loaded = store.get_node(node.id)
        assert loaded.kind == NodeKind.BUILD_SYSTEM
        assert store.get_evidence("ev:1").message == "from tool"
        assert store.get_edges_from(node.id, None, 10)[0].kind == EdgeKind.RUNS

        idx_rows = store.connection.execute("PRAGMA index_list(nodes)").fetchall()
        idx_names = {row["name"] for row in idx_rows}
        assert "idx_nodes_kind_name" in idx_names

        meta = store.connection.execute("SELECT schema_version FROM meta WHERE id=1").fetchone()
        assert meta["schema_version"] == 1

        store.close()
