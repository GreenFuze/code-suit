from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Generic, TypeVar

from suitcode.providers.shared.lsp import LspClient
from suitcode.providers.shared.lsp_code.backend import LspCodeBackend, LspRepositorySymbol
from suitcode.providers.shared.lsp_code.session import LspResolver, LspSessionManager

if TYPE_CHECKING:
    from suitcode.core.repository import Repository

_SymbolT = TypeVar("_SymbolT")


class LspSymbolServiceBase(Generic[_SymbolT]):
    def __init__(
        self,
        repository: Repository,
        *,
        ensure_ready: Callable[[], None],
        resolver: LspResolver,
        supported_extensions: frozenset[str],
        symbol_kind_by_code: dict[int, str],
        ignored_directories: frozenset[str],
        symbol_factory: Callable[[LspRepositorySymbol], _SymbolT],
        client_factory: Callable[..., LspClient] | None = None,
        session_manager: LspSessionManager | None = None,
    ) -> None:
        self._symbol_factory = symbol_factory
        self._backend = LspCodeBackend(
            repository_root=repository.root,
            ensure_ready=ensure_ready,
            resolver=resolver,
            supported_extensions=supported_extensions,
            symbol_kind_by_code=symbol_kind_by_code,
            ignored_directories=ignored_directories,
            client_factory=client_factory,
            session_manager=session_manager,
        )

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[_SymbolT, ...]:
        return tuple(
            self._symbol_factory(item)
            for item in self._backend.get_symbols(query, is_case_sensitive=is_case_sensitive)
        )

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[_SymbolT, ...]:
        return tuple(
            self._symbol_factory(item)
            for item in self._backend.list_file_symbols(
                repository_rel_path,
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._backend.find_definition(repository_rel_path, line, column)

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._backend.find_references(
            repository_rel_path,
            line,
            column,
            include_definition=include_definition,
        )
