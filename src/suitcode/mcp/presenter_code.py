from __future__ import annotations

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import EntityInfo
from suitcode.mcp.models import LocationView, SymbolView
from suitcode.mcp.presenter_common import provenance_views


class CodePresenter:
    def symbol_view(self, entity: EntityInfo) -> SymbolView:
        return SymbolView(
            id=entity.id,
            name=entity.name,
            kind=entity.entity_kind,
            path=entity.repository_rel_path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            column_start=entity.column_start,
            column_end=entity.column_end,
            signature=entity.signature,
            provenance=provenance_views(entity.provenance),
        )

    def location_view(self, location: CodeLocation) -> LocationView:
        return LocationView(
            path=location.repository_rel_path,
            line_start=location.line_start,
            line_end=location.line_end,
            column_start=location.column_start,
            column_end=location.column_end,
            symbol_id=location.symbol_id,
            provenance=provenance_views(location.provenance),
        )
