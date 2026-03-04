from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import EntityInfo
from suitcode.core.ownership_index import OwnershipIndex

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class CodeReferenceService:
    def __init__(self, repository: Repository, ownership_index: OwnershipIndex) -> None:
        self._repository = repository
        self._ownership_index = ownership_index

    def resolve_symbol(self, symbol_id: str) -> EntityInfo:
        if not symbol_id.startswith("entity:"):
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        parts = symbol_id.split(":")
        if len(parts) < 4:
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        repository_rel_path = parts[1]
        matches = [item for item in self._repository.code.list_symbols_in_file(repository_rel_path) if item.id == symbol_id]
        if not matches:
            raise ValueError(f"symbol id could not be resolved: `{symbol_id}`")
        if len(matches) > 1:
            raise ValueError(f"symbol id resolved ambiguously: `{symbol_id}`")
        return matches[0]

    def references_for_file(self, repository_rel_path: str) -> tuple[CodeLocation, ...]:
        references: dict[tuple[str, int, int, int | None, int | None, str | None], CodeLocation] = {}
        for symbol in self._repository.code.list_symbols_in_file(repository_rel_path):
            for location in self._repository.code.find_references_by_symbol_id(symbol.id):
                key = self._location_key(location)
                references.setdefault(key, location)
        return tuple(sorted(references.values(), key=self._location_sort_key))

    def references_for_owner(self, owner_id: str) -> tuple[CodeLocation, ...]:
        references: dict[tuple[str, int, int, int | None, int | None, str | None], CodeLocation] = {}
        for file_info in self._ownership_index.files_for_owner(owner_id):
            for location in self.references_for_file(file_info.repository_rel_path):
                key = self._location_key(location)
                references.setdefault(key, location)
        return tuple(sorted(references.values(), key=self._location_sort_key))

    @staticmethod
    def _location_key(location: CodeLocation) -> tuple[str, int, int, int | None, int | None, str | None]:
        return (
            location.repository_rel_path,
            location.line_start,
            location.column_start,
            location.line_end,
            location.column_end,
            location.symbol_id,
        )

    @staticmethod
    def _location_sort_key(location: CodeLocation) -> tuple[str, int, int, str]:
        return (location.repository_rel_path, location.line_start, location.column_start, location.symbol_id or "")
