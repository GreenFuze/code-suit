from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PythonSymbolQuery:
    query: str


@dataclass(frozen=True)
class PythonWorkspaceSymbol:
    name: str
    kind: str
    repository_rel_path: str
    line_start: int | None
    line_end: int | None
    column_start: int | None
    column_end: int | None
    container_name: str | None
    signature: str | None
