from __future__ import annotations

from suitcode.providers.shared.lsp.errors import LspProtocolError
from suitcode.providers.shared.lsp.messages import (
    LspDocumentSymbol,
    LspLocationLink,
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

    def parse_locations(self, payload: object) -> tuple[LspLocation, ...]:
        if payload is None:
            return tuple()
        if isinstance(payload, dict):
            if "uri" in payload:
                return (self._parse_location(payload),)
            if "targetUri" in payload:
                link = self._parse_location_link(payload)
                return (LspLocation(uri=link.target_uri, range=link.target_selection_range or link.target_range),)
            raise LspProtocolError("location response object must be a Location or LocationLink")
        if not isinstance(payload, list):
            raise LspProtocolError("definition/reference response must be a location, a list of locations, or null")
        parsed: list[LspLocation] = []
        for item in payload:
            if not isinstance(item, dict):
                raise LspProtocolError("definition/reference list items must be objects")
            if "uri" in item:
                parsed.append(self._parse_location(item))
            elif "targetUri" in item:
                link = self._parse_location_link(item)
                parsed.append(LspLocation(uri=link.target_uri, range=link.target_selection_range or link.target_range))
            else:
                raise LspProtocolError("definition/reference list items must be Location or LocationLink objects")
        return tuple(parsed)

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
        if "location" in payload:
            return self._parse_document_symbol_information(payload)
        name = payload.get("name")
        kind = payload.get("kind")
        detail = payload.get("detail")
        container_name = payload.get("containerName")
        children_payload = payload.get("children", [])
        if not isinstance(name, str):
            raise LspProtocolError("document symbol name must be a string")
        if not isinstance(kind, int):
            raise LspProtocolError("document symbol kind must be an integer")
        if detail is not None and not isinstance(detail, str):
            raise LspProtocolError("document symbol detail must be a string when present")
        if container_name is not None and not isinstance(container_name, str):
            raise LspProtocolError("document symbol containerName must be a string when present")
        if not isinstance(children_payload, list):
            raise LspProtocolError("document symbol children must be a list when present")
        return LspDocumentSymbol(
            name=name,
            kind=kind,
            range=self._parse_range(payload.get("range")),
            selection_range=self._parse_range(payload.get("selectionRange")),
            detail=detail,
            container_name=container_name,
            children=tuple(self._parse_document_symbol(item) for item in children_payload),
        )

    def _parse_document_symbol_information(self, payload: object) -> LspDocumentSymbol:
        if not isinstance(payload, dict):
            raise LspProtocolError("document symbol payload must be an object")
        name = payload.get("name")
        kind = payload.get("kind")
        container_name = payload.get("containerName")
        if not isinstance(name, str):
            raise LspProtocolError("document symbol name must be a string")
        if not isinstance(kind, int):
            raise LspProtocolError("document symbol kind must be an integer")
        if container_name is not None and not isinstance(container_name, str):
            raise LspProtocolError("document symbol containerName must be a string when present")
        location = self._parse_location(payload.get("location"))
        return LspDocumentSymbol(
            name=name,
            kind=kind,
            range=location.range,
            selection_range=location.range,
            container_name=container_name,
            children=tuple(),
        )

    def _parse_location(self, payload: object) -> LspLocation:
        if not isinstance(payload, dict):
            raise LspProtocolError("location payload must be an object")
        uri = payload.get("uri")
        range_payload = payload.get("range")
        if not isinstance(uri, str):
            raise LspProtocolError("location uri must be a string")
        return LspLocation(uri=uri, range=self._parse_range(range_payload))

    def _parse_location_link(self, payload: object) -> LspLocationLink:
        if not isinstance(payload, dict):
            raise LspProtocolError("location link payload must be an object")
        target_uri = payload.get("targetUri")
        target_range_payload = payload.get("targetRange")
        target_selection_range_payload = payload.get("targetSelectionRange")
        if not isinstance(target_uri, str):
            raise LspProtocolError("location link targetUri must be a string")
        if target_range_payload is None:
            raise LspProtocolError("location link targetRange is required")
        return LspLocationLink(
            target_uri=target_uri,
            target_range=self._parse_range(target_range_payload),
            target_selection_range=(
                self._parse_range(target_selection_range_payload)
                if target_selection_range_payload is not None
                else None
            ),
        )

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
