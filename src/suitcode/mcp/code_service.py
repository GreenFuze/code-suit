from __future__ import annotations

from suitcode.core.code.models import SymbolLookupTarget
from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import ListResult, LocationView, SymbolView
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import CodePresenter
from suitcode.mcp.state import WorkspaceRegistry


class CodeMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        code_presenter: CodePresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._code_presenter = code_presenter

    def find_symbols(
        self,
        workspace_id: str,
        repository_id: str,
        query: str,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            items = tuple(
                self._code_presenter.symbol_view(item)
                for item in repository.code.get_symbol(query, is_case_sensitive=is_case_sensitive)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def list_symbols_in_file(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        if query is not None and not query.strip():
            raise McpValidationError("query must not be blank")
        try:
            items = tuple(
                self._code_presenter.symbol_view(item)
                for item in repository.code.list_symbols_in_file(
                    repository_rel_path,
                    query=query,
                    is_case_sensitive=is_case_sensitive,
                )
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def find_definition(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = SymbolLookupTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                line=line,
                column=column,
            )
            items = tuple(self._code_presenter.location_view(item) for item in repository.code.find_definition(target))
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def find_references(
        self,
        workspace_id: str,
        repository_id: str,
        include_definition: bool = False,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = SymbolLookupTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                line=line,
                column=column,
            )
            items = tuple(
                self._code_presenter.location_view(item)
                for item in repository.code.find_references(target, include_definition=include_definition)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)
