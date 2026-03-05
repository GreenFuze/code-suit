from __future__ import annotations

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import EntityInfo, make_entity_id, normalize_repository_relative_path
from suitcode.core.provenance_builders import lsp_location_provenance, lsp_node_provenance
from suitcode.providers.shared.lsp_code.backend import LspRepositorySymbol


class LspEntityTranslatorBase:
    def __init__(self, *, source_tool: str, evidence_summary: str) -> None:
        self._source_tool = source_tool
        self._evidence_summary = evidence_summary

    def to_entity_info(self, symbol: LspRepositorySymbol) -> EntityInfo:
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
                lsp_node_provenance(
                    source_tool=self._source_tool,
                    evidence_summary=self._evidence_summary,
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )


class LspLocationTranslatorBase:
    def __init__(self, *, source_tool: str) -> None:
        self._source_tool = source_tool

    def to_code_location(
        self,
        location: tuple[str, int, int, int, int],
        *,
        operation: str,
    ) -> CodeLocation:
        repository_rel_path, line_start, line_end, column_start, column_end = location
        repository_rel_path = normalize_repository_relative_path(repository_rel_path)
        return CodeLocation(
            repository_rel_path=repository_rel_path,
            line_start=line_start,
            line_end=line_end,
            column_start=column_start,
            column_end=column_end,
            provenance=(
                lsp_location_provenance(
                    source_tool=self._source_tool,
                    repository_rel_path=repository_rel_path,
                    operation=operation,
                ),
            ),
        )
