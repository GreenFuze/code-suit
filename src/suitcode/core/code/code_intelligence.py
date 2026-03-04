from __future__ import annotations

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget
from suitcode.core.models import EntityInfo
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole


class CodeIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[CodeProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_role(ProviderRole.CODE)
            if isinstance(provider, CodeProviderBase)
        )

    def get_symbol(self, query: str, is_case_sensitive: bool = False) -> tuple[EntityInfo, ...]:
        items = [item for provider in self.providers for item in provider.get_symbol(query, is_case_sensitive=is_case_sensitive)]
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def list_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        items = [
            item
            for provider in self.providers
            for item in provider.list_symbols_in_file(
                normalized_path,
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        ]
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.entity_kind, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def find_definition(self, target: SymbolLookupTarget) -> tuple[CodeLocation, ...]:
        repository_rel_path, line, column = self._resolve_lookup_target(target)
        items = [
            item
            for provider in self.providers
            for item in provider.find_definition(repository_rel_path, line, column)
        ]
        return tuple(
            sorted(
                items,
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def find_references(
        self,
        target: SymbolLookupTarget,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        repository_rel_path, line, column = self._resolve_lookup_target(target)
        items = [
            item
            for provider in self.providers
            for item in provider.find_references(
                repository_rel_path,
                line,
                column,
                include_definition=include_definition,
            )
        ]
        return tuple(
            sorted(
                items,
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def _resolve_lookup_target(self, target: SymbolLookupTarget) -> tuple[str, int, int]:
        if target.symbol_id is not None:
            return self._resolve_symbol_target(target.symbol_id)
        assert target.repository_rel_path is not None
        assert target.line is not None
        assert target.column is not None
        return target.repository_rel_path, target.line, target.column

    def _resolve_symbol_target(self, symbol_id: str) -> tuple[str, int, int]:
        if not symbol_id.startswith("entity:"):
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        parts = symbol_id.split(":")
        if len(parts) < 4:
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        repository_rel_path = normalize_repository_relative_path(parts[1])
        matches = [item for item in self.list_symbols_in_file(repository_rel_path) if item.id == symbol_id]
        if not matches:
            raise ValueError(f"symbol id could not be resolved: `{symbol_id}`")
        if len(matches) > 1:
            raise ValueError(f"symbol id resolved ambiguously: `{symbol_id}`")
        match = matches[0]
        if match.line_start is None or match.column_start is None:
            raise ValueError(f"symbol id has no usable location: `{symbol_id}`")
        return repository_rel_path, match.line_start, match.column_start


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
