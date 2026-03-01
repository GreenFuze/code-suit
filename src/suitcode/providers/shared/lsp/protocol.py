from __future__ import annotations

from suitcode.providers.shared.lsp.errors import LspProtocolError
from suitcode.providers.shared.lsp.messages import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)


class LspProtocolParser:
    def parse_workspace_symbols(self, payload: object) -> tuple[LspWorkspaceSymbol, ...]:
        if payload is None:
            return tuple()
        if not isinstance(payload, list):
            raise LspProtocolError("workspace/symbol response must be a list or null")
        return tuple(self._parse_workspace_symbol(item) for item in payload)

    def parse_document_symbols(self, payload: object) -> tuple[LspDocumentSymbol, ...]:
        if payload is None:
            return tuple()
        if not isinstance(payload, list):
            raise LspProtocolError("textDocument/documentSymbol response must be a list or null")
        return tuple(self._parse_document_symbol(item) for item in payload)

    def _parse_workspace_symbol(self, payload: object) -> LspWorkspaceSymbol:
        if not isinstance(payload, dict):
            raise LspProtocolError("workspace symbol payload must be an object")
        name = payload.get("name")
        kind = payload.get("kind")
        if not isinstance(name, str):
            raise LspProtocolError("workspace symbol name must be a string")
        if not isinstance(kind, int):
            raise LspProtocolError("workspace symbol kind must be an integer")
        location_payload = payload.get("location")
        container_name = payload.get("containerName")
        if container_name is not None and not isinstance(container_name, str):
            raise LspProtocolError("workspace symbol containerName must be a string when present")
        return LspWorkspaceSymbol(
            name=name,
            kind=kind,
            location=self._parse_location(location_payload) if location_payload is not None else None,
            container_name=container_name,
        )

    def _parse_document_symbol(self, payload: object) -> LspDocumentSymbol:
        if not isinstance(payload, dict):
            raise LspProtocolError("document symbol payload must be an object")
        name = payload.get("name")
        kind = payload.get("kind")
        detail = payload.get("detail")
        children_payload = payload.get("children", [])
        if not isinstance(name, str):
            raise LspProtocolError("document symbol name must be a string")
        if not isinstance(kind, int):
            raise LspProtocolError("document symbol kind must be an integer")
        if detail is not None and not isinstance(detail, str):
            raise LspProtocolError("document symbol detail must be a string when present")
        if not isinstance(children_payload, list):
            raise LspProtocolError("document symbol children must be a list when present")
        return LspDocumentSymbol(
            name=name,
            kind=kind,
            range=self._parse_range(payload.get("range")),
            selection_range=self._parse_range(payload.get("selectionRange")),
            detail=detail,
            children=tuple(self._parse_document_symbol(item) for item in children_payload),
        )

    def _parse_location(self, payload: object) -> LspLocation:
        if not isinstance(payload, dict):
            raise LspProtocolError("location payload must be an object")
        uri = payload.get("uri")
        range_payload = payload.get("range")
        if not isinstance(uri, str):
            raise LspProtocolError("location uri must be a string")
        return LspLocation(uri=uri, range=self._parse_range(range_payload))

    def _parse_range(self, payload: object) -> LspRange:
        if not isinstance(payload, dict):
            raise LspProtocolError("range payload must be an object")
        return LspRange(
            start=self._parse_position(payload.get("start")),
            end=self._parse_position(payload.get("end")),
        )

    def _parse_position(self, payload: object) -> LspPosition:
        if not isinstance(payload, dict):
            raise LspProtocolError("position payload must be an object")
        line = payload.get("line")
        character = payload.get("character")
        if not isinstance(line, int) or not isinstance(character, int):
            raise LspProtocolError("position line and character must be integers")
        return LspPosition(line=line, character=character)
