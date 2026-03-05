from __future__ import annotations

from abc import abstractmethod

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import EntityInfo


class CodeFacadeMixin:
    def get_symbol(self, query: str, is_case_sensitive: bool = False) -> tuple[EntityInfo, ...]:
        return tuple(
            sorted(
                (self._to_entity_info(item) for item in self._get_symbols(query, is_case_sensitive=is_case_sensitive)),
                key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def list_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        return tuple(
            sorted(
                (
                    self._to_entity_info(item)
                    for item in self._list_file_symbols(
                        repository_rel_path,
                        query=query,
                        is_case_sensitive=is_case_sensitive,
                    )
                ),
                key=lambda item: (item.name, item.entity_kind, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[CodeLocation, ...]:
        return tuple(
            self._to_code_location(item, operation="definition")
            for item in self._find_definition_locations(repository_rel_path, line, column)
        )

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        return tuple(
            self._to_code_location(item, operation="references")
            for item in self._find_reference_locations(
                repository_rel_path,
                line,
                column,
                include_definition=include_definition,
            )
        )

    @abstractmethod
    def _get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[object, ...]:
        raise NotImplementedError

    @abstractmethod
    def _list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[object, ...]:
        raise NotImplementedError

    @abstractmethod
    def _find_definition_locations(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        raise NotImplementedError

    @abstractmethod
    def _find_reference_locations(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        raise NotImplementedError

    @abstractmethod
    def _to_entity_info(self, symbol: object) -> EntityInfo:
        raise NotImplementedError

    @abstractmethod
    def _to_code_location(
        self,
        location: tuple[str, int, int, int, int],
        *,
        operation: str,
    ) -> CodeLocation:
        raise NotImplementedError
