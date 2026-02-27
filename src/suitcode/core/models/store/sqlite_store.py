from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from suitcode.core.models.edges import Edge, EdgeKey
from suitcode.core.models.errors import GraphNotFoundError, GraphStoreError
from suitcode.core.models.graph_types import EdgeKind, EvidenceId, NodeId, NodeKind
from suitcode.core.models.nodes import Evidence, GraphNode, parse_node
from suitcode.core.models.serialization import (
    edge_payload_json,
    evidence_payload_json,
    node_payload_json,
    sha256_hex,
)
from suitcode.core.models.store.interfaces import GraphStore
from suitcode.core.models.store.migrations import apply_migrations


class SQLiteGraphStore(GraphStore):
    def __init__(self, db_path: Path, workspace_root: Path) -> None:
        self.db_path = db_path
        self.workspace_root = workspace_root
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise GraphStoreError(
                "store is not initialized",
                remediation="Call initialize() before using the store.",
                db_path=self.db_path,
            )
        return self._connection

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 3000")
        connection.execute("PRAGMA foreign_keys = ON")
        self._connection = connection
        apply_migrations(connection, self.workspace_root)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def begin(self) -> None:
        self.connection.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    @contextmanager
    def transaction(self):
        self.begin()
        try:
            yield
            self.commit()
        except Exception:
            self.rollback()
            raise

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def upsert_node(self, node: GraphNode, scope: str) -> None:
        payload_json = node_payload_json(node)
        payload_sha = sha256_hex(payload_json)
        self.connection.execute(
            """
            INSERT INTO nodes(id, kind, name, payload_json, payload_sha, updated_at, scope)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                name = excluded.name,
                payload_json = excluded.payload_json,
                payload_sha = excluded.payload_sha,
                updated_at = excluded.updated_at,
                scope = excluded.scope
            """,
            (node.id, node.kind, node.name, payload_json, payload_sha, self._now(), scope),
        )

    def delete_node(self, node_id: NodeId) -> None:
        row = self.connection.execute(
            "SELECT 1 FROM edges WHERE src = ? OR dst = ? LIMIT 1", (node_id, node_id)
        ).fetchone()
        if row is not None:
            raise GraphStoreError(
                f"cannot delete node {node_id}; edges still reference it",
                remediation="Delete referencing edges first.",
                db_path=self.db_path,
            )
        deleted = self.connection.execute("DELETE FROM nodes WHERE id = ?", (node_id,)).rowcount
        if deleted == 0:
            raise GraphNotFoundError(
                f"node not found: {node_id}",
                remediation="Check node id before deletion.",
                db_path=self.db_path,
            )

    def upsert_edge(self, edge: Edge, scope: str) -> None:
        payload_json = edge_payload_json(edge)
        payload_sha = sha256_hex(payload_json)
        self.connection.execute(
            """
            INSERT INTO edges(src, kind, dst, payload_json, payload_sha, updated_at, scope)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(src, kind, dst) DO UPDATE SET
                payload_json = excluded.payload_json,
                payload_sha = excluded.payload_sha,
                updated_at = excluded.updated_at,
                scope = excluded.scope
            """,
            (edge.src, edge.kind, edge.dst, payload_json, payload_sha, self._now(), scope),
        )

    def delete_edge(self, src: NodeId, kind: EdgeKind, dst: NodeId) -> None:
        deleted = self.connection.execute(
            "DELETE FROM edges WHERE src = ? AND kind = ? AND dst = ?",
            (src, kind, dst),
        ).rowcount
        if deleted == 0:
            raise GraphNotFoundError(
                f"edge not found: {kind}:{src}->{dst}",
                remediation="Check edge key before deletion.",
                db_path=self.db_path,
            )

    def upsert_evidence(self, evidence: Evidence, scope: str) -> None:
        payload_json = evidence_payload_json(evidence)
        payload_sha = sha256_hex(payload_json)
        self.connection.execute(
            """
            INSERT INTO evidence(id, payload_json, payload_sha, updated_at, scope)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json = excluded.payload_json,
                payload_sha = excluded.payload_sha,
                updated_at = excluded.updated_at,
                scope = excluded.scope
            """,
            (evidence.id, payload_json, payload_sha, self._now(), scope),
        )

    def get_node(self, node_id: NodeId) -> GraphNode:
        row = self.connection.execute("SELECT payload_json FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            raise GraphNotFoundError(
                f"node not found: {node_id}",
                remediation="Check node id before lookup.",
                db_path=self.db_path,
            )
        payload = json.loads(row["payload_json"])
        return parse_node(payload)

    def get_evidence(self, evidence_id: EvidenceId) -> Evidence:
        row = self.connection.execute(
            "SELECT payload_json FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        if row is None:
            raise GraphNotFoundError(
                f"evidence not found: {evidence_id}",
                remediation="Check evidence id before lookup.",
                db_path=self.db_path,
            )
        return Evidence.model_validate(json.loads(row["payload_json"]))

    def _edges_query(
        self,
        column: str,
        value: NodeId,
        kinds: set[EdgeKind] | None,
        limit: int,
    ) -> tuple[Edge, ...]:
        if limit <= 0:
            return tuple()
        base = f"SELECT payload_json FROM edges WHERE {column} = ?"
        params: list[object] = [value]
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            base += f" AND kind IN ({placeholders})"
            params.extend(sorted(kinds))
        base += " ORDER BY kind, src, dst LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(base, tuple(params)).fetchall()
        return tuple(Edge.model_validate(json.loads(row["payload_json"])) for row in rows)

    def get_edges_from(self, src: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]:
        return self._edges_query("src", src, kinds, limit)

    def get_edges_to(self, dst: NodeId, kinds: set[EdgeKind] | None, limit: int) -> tuple[Edge, ...]:
        return self._edges_query("dst", dst, kinds, limit)

    def list_nodes(self, kind: NodeKind | None, limit: int) -> tuple[GraphNode, ...]:
        if limit <= 0:
            return tuple()
        if kind is None:
            rows = self.connection.execute(
                "SELECT payload_json FROM nodes ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload_json FROM nodes WHERE kind = ? ORDER BY id LIMIT ?",
                (kind, limit),
            ).fetchall()
        return tuple(parse_node(json.loads(row["payload_json"])) for row in rows)

    def find_nodes_by_name(self, name: str, *, exact: bool, limit: int) -> tuple[GraphNode, ...]:
        if limit <= 0:
            return tuple()
        if exact:
            rows = self.connection.execute(
                "SELECT payload_json FROM nodes WHERE name = ? ORDER BY id LIMIT ?",
                (name, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload_json FROM nodes WHERE name LIKE ? ORDER BY id LIMIT ?",
                (f"{name}%", limit),
            ).fetchall()
        return tuple(parse_node(json.loads(row["payload_json"])) for row in rows)

    def purge_scope(self, scope: str) -> None:
        self.connection.execute("DELETE FROM edges WHERE scope = ?", (scope,))
        self.connection.execute("DELETE FROM nodes WHERE scope = ?", (scope,))
        self.connection.execute("DELETE FROM evidence WHERE scope = ?", (scope,))

    def iter_scope_node_ids(self, scope: str) -> Iterator[NodeId]:
        rows = self.connection.execute("SELECT id FROM nodes WHERE scope = ?", (scope,)).fetchall()
        for row in rows:
            yield row["id"]

    def iter_scope_edges(self, scope: str) -> Iterator[EdgeKey]:
        rows = self.connection.execute(
            "SELECT src, kind, dst FROM edges WHERE scope = ? ORDER BY kind, src, dst",
            (scope,),
        ).fetchall()
        for row in rows:
            yield (row["src"], EdgeKind(row["kind"]), row["dst"])

    def iter_scope_evidence_ids(self, scope: str) -> Iterator[EvidenceId]:
        rows = self.connection.execute("SELECT id FROM evidence WHERE scope = ?", (scope,)).fetchall()
        for row in rows:
            yield row["id"]

    def purge_scope_not_seen(
        self,
        scope: str,
        seen_node_ids: set[NodeId],
        seen_edge_keys: set[EdgeKey],
        seen_evidence_ids: set[EvidenceId],
    ) -> None:
        for src, kind, dst in list(self.iter_scope_edges(scope)):
            if (src, kind, dst) not in seen_edge_keys:
                self.connection.execute(
                    "DELETE FROM edges WHERE src = ? AND kind = ? AND dst = ?",
                    (src, kind, dst),
                )

        for node_id in list(self.iter_scope_node_ids(scope)):
            if node_id not in seen_node_ids:
                self.connection.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

        for evidence_id in list(self.iter_scope_evidence_ids(scope)):
            if evidence_id not in seen_evidence_ids:
                self.connection.execute("DELETE FROM evidence WHERE id = ?", (evidence_id,))


    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

