from __future__ import annotations

from fnmatch import fnmatchcase
from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import SymbolLookupHit
from suitcode.core.models import EntityInfo
from suitcode.core.provenance_builders import lsp_location_provenance
from suitcode.core.provenance_summary import preferred_source_tool
from suitcode.core.tests.models import RelatedTestTarget

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class SymbolLookupService:
    _REFERENCE_PREVIEW_LIMIT = 3
    _RELATED_TEST_PREVIEW_LIMIT = 2

    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    def find_symbols(
        self,
        query: str,
        *,
        is_case_sensitive: bool = False,
    ) -> tuple[SymbolLookupHit, ...]:
        hits = tuple(
            self._build_hit(symbol)
            for symbol in self._repository.code.get_symbol(query, is_case_sensitive=is_case_sensitive)
        )
        ranked = sorted(
            hits,
            key=lambda item: self._rank_key(
                item,
                query=query,
                is_case_sensitive=is_case_sensitive,
            ),
        )
        return tuple(ranked)

    def _build_hit(self, symbol: EntityInfo) -> SymbolLookupHit:
        owner = self._resolve_owner(symbol.repository_rel_path)
        definition_anchor = self._definition_anchor(symbol)
        external_references = self._external_references(symbol)
        related_tests = self._related_tests(symbol.repository_rel_path)
        return SymbolLookupHit(
            symbol=symbol,
            owner=owner,
            reference_count=len(external_references),
            reference_preview=external_references[: self._REFERENCE_PREVIEW_LIMIT],
            related_tests_preview=related_tests[: self._RELATED_TEST_PREVIEW_LIMIT],
            definition_anchor=definition_anchor,
            context_source=self._context_source(
                owner=owner is not None,
                has_references=bool(external_references),
                has_related_tests=bool(related_tests),
            ),
            provenance=self._merged_provenance(
                symbol.provenance,
                definition_anchor.provenance if definition_anchor is not None else tuple(),
                *(location.provenance for location in external_references),
                *(test.provenance for test in related_tests),
            ),
        )

    def _resolve_owner(self, repository_rel_path: str):
        try:
            return self._repository.get_file_owner(repository_rel_path).owner
        except ValueError:
            return None

    def _definition_anchor(self, symbol: EntityInfo) -> CodeLocation | None:
        try:
            definitions = self._repository.code.find_definition_by_symbol_id(symbol.id)
        except ValueError:
            definitions = tuple()
        if definitions:
            return definitions[0]
        if symbol.line_start is None or symbol.column_start is None:
            return None
        source_tool = preferred_source_tool(symbol.provenance) or "lsp"
        return CodeLocation(
            repository_rel_path=symbol.repository_rel_path,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            column_start=symbol.column_start,
            column_end=symbol.column_end,
            symbol_id=symbol.id,
            provenance=(
                lsp_location_provenance(
                    source_tool=source_tool,
                    repository_rel_path=symbol.repository_rel_path,
                    operation="definition",
                ),
            ),
        )

    def _external_references(self, symbol: EntityInfo) -> tuple[CodeLocation, ...]:
        try:
            references = self._repository.code.find_references_by_symbol_id(symbol.id)
        except ValueError:
            return tuple()
        return tuple(
            item
            for item in references
            if item.repository_rel_path != symbol.repository_rel_path
        )

    def _related_tests(self, repository_rel_path: str):
        try:
            tests = self._repository.tests.get_related_tests(
                RelatedTestTarget(repository_rel_path=repository_rel_path)
            )
        except ValueError:
            return tuple()
        return tuple(item for item in tests if item.is_authoritative)

    @staticmethod
    def _context_source(*, owner: bool, has_references: bool, has_related_tests: bool) -> str:
        parts = ["symbol"]
        if owner:
            parts.append("owner")
        if has_references:
            parts.append("references")
        if has_related_tests:
            parts.append("related_tests")
        return " + ".join(parts)

    def _rank_key(
        self,
        item: SymbolLookupHit,
        *,
        query: str,
        is_case_sensitive: bool,
    ) -> tuple[int, int, int, str, int, int, str]:
        return (
            -int(self._is_exact_name_match(item.symbol.name, query, is_case_sensitive)),
            -int(item.reference_count > 0),
            -int(bool(item.related_tests_preview)),
            item.symbol.repository_rel_path,
            item.symbol.line_start or 10**9,
            item.symbol.column_start or 10**9,
            item.symbol.id,
        )

    @staticmethod
    def _is_exact_name_match(symbol_name: str, query: str, is_case_sensitive: bool) -> bool:
        candidate_name = symbol_name if is_case_sensitive else symbol_name.casefold()
        candidate_query = query if is_case_sensitive else query.casefold()
        if "*" in query or "?" in query:
            if not fnmatchcase(candidate_name, candidate_query):
                return False
            return False
        return candidate_name == candidate_query

    @staticmethod
    def _merged_provenance(*groups) -> tuple:
        merged = []
        for group in groups:
            for entry in group:
                if entry in merged:
                    continue
                merged.append(entry)
        return tuple(merged)
