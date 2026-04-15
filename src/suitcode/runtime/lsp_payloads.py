from __future__ import annotations

from suitcode.providers.shared.lsp import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)


def workspace_symbols_to_payload(items: tuple[LspWorkspaceSymbol, ...]) -> tuple[dict[str, object], ...]:
    return tuple(_workspace_symbol_to_dict(item) for item in items)


def workspace_symbols_from_payload(items: tuple[dict[str, object], ...]) -> tuple[LspWorkspaceSymbol, ...]:
    return tuple(_workspace_symbol_from_dict(item) for item in items)


def document_symbols_to_payload(items: tuple[LspDocumentSymbol, ...]) -> tuple[dict[str, object], ...]:
    return tuple(_document_symbol_to_dict(item) for item in items)


def document_symbols_from_payload(items: tuple[dict[str, object], ...]) -> tuple[LspDocumentSymbol, ...]:
    return tuple(_document_symbol_from_dict(item) for item in items)


def locations_to_payload(items: tuple[LspLocation, ...]) -> tuple[dict[str, object], ...]:
    return tuple(_location_to_dict(item) for item in items)


def locations_from_payload(items: tuple[dict[str, object], ...]) -> tuple[LspLocation, ...]:
    return tuple(_location_from_dict(item) for item in items)


def _workspace_symbol_to_dict(item: LspWorkspaceSymbol) -> dict[str, object]:
    return {
        "name": item.name,
        "kind": item.kind,
        "container_name": item.container_name,
        "location": None if item.location is None else _location_to_dict(item.location),
    }


def _workspace_symbol_from_dict(item: dict[str, object]) -> LspWorkspaceSymbol:
    location_payload = item.get("location")
    if location_payload is not None and not isinstance(location_payload, dict):
        raise ValueError("workspace symbol location payload must be an object when present")
    return LspWorkspaceSymbol(
        name=_require_str(item, "name"),
        kind=_require_int(item, "kind"),
        container_name=_optional_str(item, "container_name"),
        location=None if location_payload is None else _location_from_dict(location_payload),
    )


def _document_symbol_to_dict(item: LspDocumentSymbol) -> dict[str, object]:
    return {
        "name": item.name,
        "kind": item.kind,
        "detail": item.detail,
        "container_name": item.container_name,
        "range": _range_to_dict(item.range),
        "selection_range": _range_to_dict(item.selection_range),
        "children": tuple(_document_symbol_to_dict(child) for child in item.children),
    }


def _document_symbol_from_dict(item: dict[str, object]) -> LspDocumentSymbol:
    children_payload = item.get("children")
    if not isinstance(children_payload, (list, tuple)):
        raise ValueError("document symbol children payload must be a list")
    return LspDocumentSymbol(
        name=_require_str(item, "name"),
        kind=_require_int(item, "kind"),
        detail=_optional_str(item, "detail"),
        container_name=_optional_str(item, "container_name"),
        range=_range_from_dict(_require_dict(item, "range")),
        selection_range=_range_from_dict(_require_dict(item, "selection_range")),
        children=tuple(_document_symbol_from_dict(child) for child in children_payload if isinstance(child, dict)),
    )


def _location_to_dict(item: LspLocation) -> dict[str, object]:
    return {
        "uri": item.uri,
        "range": _range_to_dict(item.range),
    }


def _location_from_dict(item: dict[str, object]) -> LspLocation:
    return LspLocation(
        uri=_require_str(item, "uri"),
        range=_range_from_dict(_require_dict(item, "range")),
    )


def _range_to_dict(item: LspRange) -> dict[str, object]:
    return {
        "start": _position_to_dict(item.start),
        "end": _position_to_dict(item.end),
    }


def _range_from_dict(item: dict[str, object]) -> LspRange:
    return LspRange(
        start=_position_from_dict(_require_dict(item, "start")),
        end=_position_from_dict(_require_dict(item, "end")),
    )


def _position_to_dict(item: LspPosition) -> dict[str, object]:
    return {
        "line": item.line,
        "character": item.character,
    }


def _position_from_dict(item: dict[str, object]) -> LspPosition:
    return LspPosition(
        line=_require_int(item, "line"),
        character=_require_int(item, "character"),
    )


def _require_dict(item: dict[str, object], key: str) -> dict[str, object]:
    value = item.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"payload field `{key}` must be an object")
    return value


def _require_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise ValueError(f"payload field `{key}` must be a string")
    return value


def _optional_str(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"payload field `{key}` must be a string when present")
    return value


def _require_int(item: dict[str, object], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int):
        raise ValueError(f"payload field `{key}` must be an integer")
    return value
