from __future__ import annotations

from dataclasses import replace
from pathlib import Path
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
        attachment_root: Path | None = None,
        attachment_root_rel_path: str = "",
        included_repository_rel_roots: frozenset[str] | None = None,
        enable_workspace_symbol_fallback: bool = True,
    ) -> None:
        self._symbol_factory = symbol_factory
        self._attachment_root = (attachment_root or repository.root).expanduser().resolve()
        normalized_attachment_root = attachment_root_rel_path.strip().strip("/").replace("\\", "/")
        self._attachment_root_rel_path = "" if normalized_attachment_root == "." else normalized_attachment_root
        included_roots = (
            frozenset(self._to_attachment_rel_path(path) for path in included_repository_rel_roots)
            if included_repository_rel_roots is not None
            else None
        )
        self._backend = LspCodeBackend(
            repository_root=self._attachment_root,
            ensure_ready=ensure_ready,
            resolver=resolver,
            supported_extensions=supported_extensions,
            symbol_kind_by_code=symbol_kind_by_code,
            ignored_directories=ignored_directories,
            included_roots=included_roots,
            enable_workspace_symbol_fallback=enable_workspace_symbol_fallback,
            client_factory=client_factory,
            session_manager=session_manager,
        )

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[_SymbolT, ...]:
        return tuple(
            self._symbol_factory(self._to_repository_symbol(item))
            for item in self._backend.get_symbols(query, is_case_sensitive=is_case_sensitive)
        )

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[_SymbolT, ...]:
        return tuple(
            self._symbol_factory(self._to_repository_symbol(item))
            for item in self._backend.list_file_symbols(
                self._to_attachment_rel_path(repository_rel_path),
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._rebase_locations(
            self._backend.find_definition(self._to_attachment_rel_path(repository_rel_path), line, column)
        )

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._rebase_locations(
            self._backend.find_references(
                self._to_attachment_rel_path(repository_rel_path),
                line,
                column,
                include_definition=include_definition,
            )
        )

    def find_implementations(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._rebase_locations(
            self._backend.find_implementations(self._to_attachment_rel_path(repository_rel_path), line, column)
        )

    def _to_attachment_rel_path(self, repository_rel_path: str) -> str:
        normalized = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
        if normalized == ".":
            normalized = ""
        if not self._attachment_root_rel_path:
            return normalized
        prefix = f"{self._attachment_root_rel_path}/"
        if normalized == self._attachment_root_rel_path:
            return ""
        if not normalized.startswith(prefix):
            raise ValueError(
                f"file is outside attachment `{self._attachment_root_rel_path}`: `{repository_rel_path}`"
            )
        return normalized.removeprefix(prefix)

    def _to_repository_rel_path(self, attachment_rel_path: str) -> str:
        normalized = attachment_rel_path.strip().replace("\\", "/").removeprefix("./")
        if normalized == ".":
            normalized = ""
        if not self._attachment_root_rel_path:
            return normalized
        if not normalized:
            return self._attachment_root_rel_path
        return f"{self._attachment_root_rel_path}/{normalized}"

    def _to_repository_symbol(self, symbol: LspRepositorySymbol) -> LspRepositorySymbol:
        if not self._attachment_root_rel_path:
            return symbol
        return replace(symbol, repository_rel_path=self._to_repository_rel_path(symbol.repository_rel_path))

    def _rebase_locations(
        self,
        locations: tuple[tuple[str, int, int, int, int], ...],
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return tuple(
            (self._to_repository_rel_path(path), line_start, line_end, column_start, column_end)
            for path, line_start, line_end, column_start, column_end in locations
        )
