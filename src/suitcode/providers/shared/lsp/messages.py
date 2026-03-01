from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LspPosition:
    line: int
    character: int


@dataclass(frozen=True)
class LspRange:
    start: LspPosition
    end: LspPosition


@dataclass(frozen=True)
class LspLocation:
    uri: str
    range: LspRange


@dataclass(frozen=True)
class LspWorkspaceSymbol:
    name: str
    kind: int
    location: LspLocation | None
    container_name: str | None = None


@dataclass(frozen=True)
class LspDocumentSymbol:
    name: str
    kind: int
    range: LspRange
    selection_range: LspRange
    detail: str | None = None
    children: tuple["LspDocumentSymbol", ...] = ()
