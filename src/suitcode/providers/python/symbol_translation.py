from __future__ import annotations

from suitcode.core.models import EntityInfo, make_entity_id, normalize_repository_relative_path
from suitcode.core.provenance_builders import lsp_node_provenance
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol


class PythonSymbolTranslator:
    def to_entity_info(self, symbol: PythonWorkspaceSymbol) -> EntityInfo:
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
                    source_tool="basedpyright",
                    evidence_summary="discovered from Python LSP symbol information",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )
