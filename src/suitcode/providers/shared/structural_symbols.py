from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatchcase
from typing import Protocol

from suitcode.core.models import EntityInfo, make_entity_id, normalize_repository_relative_path
from suitcode.core.provenance_builders import syntax_node_provenance


class StructuralSymbolLike(Protocol):
    name: str
    kind: str
    repository_rel_path: str
    line_start: int | None
    line_end: int | None
    column_start: int | None
    column_end: int | None
    signature: str | None


def structural_symbols_to_entities(
    symbols: Iterable[StructuralSymbolLike],
    *,
    source_tool: str,
    evidence_summary: str,
) -> tuple[EntityInfo, ...]:
    entities = tuple(
        _structural_symbol_to_entity(
            symbol,
            source_tool=source_tool,
            evidence_summary=evidence_summary,
        )
        for symbol in symbols
    )
    return tuple(
        sorted(
            entities,
            key=lambda item: (item.name, item.entity_kind, item.line_start or 0, item.column_start or 0, item.id),
        )
    )


def filter_structural_symbols(
    symbols: Iterable[StructuralSymbolLike],
    *,
    query: str | None,
    is_case_sensitive: bool,
) -> tuple[StructuralSymbolLike, ...]:
    if query is None:
        return tuple(symbols)
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("symbol query must not be empty")
    return tuple(
        symbol
        for symbol in symbols
        if _matches_query(symbol.name, normalized_query, is_case_sensitive)
    )


def _structural_symbol_to_entity(
    symbol: StructuralSymbolLike,
    *,
    source_tool: str,
    evidence_summary: str,
) -> EntityInfo:
    repository_rel_path = normalize_repository_relative_path(symbol.repository_rel_path)
    return EntityInfo(
        id=make_entity_id(
            repository_rel_path,
            symbol.kind,
            symbol.name,
            symbol.line_start,
            symbol.line_end,
        ),
        name=symbol.name,
        repository_rel_path=repository_rel_path,
        entity_kind=symbol.kind,
        line_start=symbol.line_start,
        line_end=symbol.line_end,
        column_start=symbol.column_start,
        column_end=symbol.column_end,
        signature=symbol.signature,
        provenance=(
            syntax_node_provenance(
                source_tool=source_tool,
                evidence_summary=evidence_summary,
                evidence_paths=(repository_rel_path,),
            ),
        ),
    )


def _matches_query(symbol_name: str, query: str, is_case_sensitive: bool) -> bool:
    candidate_name = symbol_name if is_case_sensitive else symbol_name.casefold()
    candidate_query = query if is_case_sensitive else query.casefold()
    if "*" in query or "?" in query:
        return fnmatchcase(candidate_name, candidate_query)
    return candidate_name == candidate_query
