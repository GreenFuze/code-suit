from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from suitcode.core.models.errors import GraphStoreError


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def apply_migrations(connection: sqlite3.Connection, workspace_root: Path) -> None:
    cursor = connection.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version INTEGER NOT NULL,
            workspace_root TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scope TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS edges (
            src TEXT NOT NULL,
            kind TEXT NOT NULL,
            dst TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scope TEXT NOT NULL,
            PRIMARY KEY(src, kind, dst)
        );

        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            payload_sha TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scope TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            config_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            logs_path TEXT,
            structural_fingerprint TEXT,
            scope TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_kind_name ON nodes(kind, name);
        CREATE INDEX IF NOT EXISTS idx_edges_src_kind ON edges(src, kind);
        CREATE INDEX IF NOT EXISTS idx_edges_dst_kind ON edges(dst, kind);
        CREATE INDEX IF NOT EXISTS idx_nodes_scope ON nodes(scope);
        CREATE INDEX IF NOT EXISTS idx_edges_scope ON edges(scope);
        """
    )

    row = cursor.execute(
        "SELECT schema_version, workspace_root FROM meta WHERE id = 1"
    ).fetchone()
    now = utc_now_iso()
    workspace_root_str = str(workspace_root)

    if row is None:
        cursor.execute(
            """
            INSERT INTO meta(id, schema_version, workspace_root, created_at, updated_at)
            VALUES(1, ?, ?, ?, ?)
            """,
            (SCHEMA_VERSION, workspace_root_str, now, now),
        )
    else:
        schema_version, existing_root = row
        if schema_version != SCHEMA_VERSION:
            raise GraphStoreError(
                (
                    f"schema version mismatch: expected {SCHEMA_VERSION}, "
                    f"found {schema_version}"
                ),
                remediation="Run a migration path or reset the workspace database.",
                db_path=workspace_root / ".suit" / "db" / "workspace.sqlite3",
            )
        if existing_root != workspace_root_str:
            raise GraphStoreError(
                "workspace_root mismatch in metadata",
                remediation="Use the database that belongs to the target repository root.",
                db_path=workspace_root / ".suit" / "db" / "workspace.sqlite3",
            )
        cursor.execute("UPDATE meta SET updated_at = ? WHERE id = 1", (now,))

    connection.commit()
