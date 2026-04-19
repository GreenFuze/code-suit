from __future__ import annotations

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import SymbolLookupHit
from suitcode.core.models import EntityInfo
from suitcode.mcp.models import LocationView, SymbolView
from suitcode.mcp.presenter_common import provenance_views


class CodePresenter:
    def __init__(self, ownership_presenter=None, test_presenter=None) -> None:
        if ownership_presenter is None:
            from suitcode.mcp.presenter_repository import OwnershipPresenter

            ownership_presenter = OwnershipPresenter()
        if test_presenter is None:
            from suitcode.mcp.presenter_tests import TestPresenter

            test_presenter = TestPresenter()
        self._ownership_presenter = ownership_presenter
        self._test_presenter = test_presenter

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
            provenance=provenance_views(entity.provenance, owner_path=entity.repository_rel_path),
        )

    def symbol_lookup_view(self, hit: SymbolLookupHit) -> SymbolView:
        symbol = hit.symbol
        return SymbolView(
            id=symbol.id,
            name=symbol.name,
            kind=symbol.entity_kind,
            path=symbol.repository_rel_path,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            column_start=symbol.column_start,
            column_end=symbol.column_end,
            signature=symbol.signature,
            owner=self._ownership_presenter.owner_view(hit.owner) if hit.owner is not None else None,
            reference_count=hit.reference_count,
            reference_preview=tuple(self.location_view(item) for item in hit.reference_preview),
            related_tests_preview=tuple(
                self._test_presenter.related_test_view(item) for item in hit.related_tests_preview
            ),
            definition_anchor=self.location_view(hit.definition_anchor) if hit.definition_anchor is not None else None,
            context_source=hit.context_source,
            provenance=provenance_views(hit.provenance, owner_path=symbol.repository_rel_path),
        )

    def location_view(self, location: CodeLocation) -> LocationView:
        return LocationView(
            path=location.repository_rel_path,
            line_start=location.line_start,
            line_end=location.line_end,
            column_start=location.column_start,
            column_end=location.column_end,
            symbol_id=location.symbol_id,
            provenance=provenance_views(location.provenance, owner_path=location.repository_rel_path),
        )
