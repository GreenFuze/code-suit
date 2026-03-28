from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.providers.go.lsp_resolution import GoplsResolver
from suitcode.providers.go.symbol_models import GoWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient
from suitcode.providers.shared.lsp_code import LspCodeBackend, LspRepositorySymbol, LspSessionManager

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class _GoSymbolServiceBase:
    _GO_EXTENSIONS = frozenset({".go"})
    _SYMBOL_KIND_BY_CODE = {
        1: "file",
        2: "module",
        3: "namespace",
        4: "package",
        5: "class",
        6: "method",
        7: "property",
        8: "field",
        9: "constructor",
        10: "enum",
        11: "interface",
        12: "function",
        13: "variable",
        14: "constant",
        23: "struct",
        24: "event",
        26: "type-parameter",
    }
    _IGNORED_DIRECTORIES = frozenset({".git", ".suit", "node_modules", "vendor"})

    def __init__(
        self,
        repository: Repository,
        *,
        attachment_root: Path,
        attachment_root_rel_path: str,
        resolver: GoplsResolver | None = None,
        client_factory: Callable[..., LspClient] | None = None,
        session_manager: LspSessionManager | None = None,
    ) -> None:
        self._repository = repository
        self._attachment_root = attachment_root.expanduser().resolve()
        normalized_attachment_root = attachment_root_rel_path.strip().strip("/").replace("\\", "/")
        self._attachment_root_rel_path = "" if normalized_attachment_root == "." else normalized_attachment_root
        self._backend = LspCodeBackend(
            repository_root=self._attachment_root,
            ensure_ready=lambda: None,
            resolver=resolver or GoplsResolver(),
            supported_extensions=self._GO_EXTENSIONS,
            symbol_kind_by_code=self._SYMBOL_KIND_BY_CODE,
            ignored_directories=self._IGNORED_DIRECTORIES,
            client_factory=client_factory,
            session_manager=session_manager,
        )

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[GoWorkspaceSymbol, ...]:
        return tuple(self._to_go_symbol(item) for item in self._backend.get_symbols(query, is_case_sensitive=is_case_sensitive))

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[GoWorkspaceSymbol, ...]:
        return tuple(
            self._to_go_symbol(item)
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

    def find_implementations(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._rebase_locations(
            self._backend.find_implementations(self._to_attachment_rel_path(repository_rel_path), line, column)
        )

    def _to_go_symbol(self, symbol: LspRepositorySymbol) -> GoWorkspaceSymbol:
        return GoWorkspaceSymbol(
            name=symbol.name,
            kind=symbol.kind,
            repository_rel_path=self._to_repository_rel_path(symbol.repository_rel_path),
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            column_start=symbol.column_start,
            column_end=symbol.column_end,
            container_name=symbol.container_name,
            signature=symbol.signature,
        )

    def _rebase_locations(self, locations: tuple[tuple[str, int, int, int, int], ...]) -> tuple[tuple[str, int, int, int, int], ...]:
        return tuple(
            (self._to_repository_rel_path(path), line_start, line_end, column_start, column_end)
            for path, line_start, line_end, column_start, column_end in locations
        )

    def _to_attachment_rel_path(self, repository_rel_path: str) -> str:
        normalized = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
        if not self._attachment_root_rel_path:
            return normalized
        prefix = f"{self._attachment_root_rel_path}/"
        if normalized == self._attachment_root_rel_path:
            return ""
        if not normalized.startswith(prefix):
            raise ValueError(
                f"file is outside Go attachment `{self._attachment_root_rel_path}`: `{repository_rel_path}`"
            )
        return normalized.removeprefix(prefix)

    def _to_repository_rel_path(self, attachment_rel_path: str) -> str:
        normalized = attachment_rel_path.strip().replace("\\", "/").removeprefix("./")
        if not self._attachment_root_rel_path:
            return normalized
        if not normalized:
            return self._attachment_root_rel_path
        return f"{self._attachment_root_rel_path}/{normalized}"


class GoSymbolService(_GoSymbolServiceBase):
    pass


class GoFileSymbolService(_GoSymbolServiceBase):
    pass
