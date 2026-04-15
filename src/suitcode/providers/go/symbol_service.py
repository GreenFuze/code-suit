from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.providers.go.lsp_resolution import GoplsResolver
from suitcode.providers.go.symbol_models import GoWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient
from suitcode.providers.shared.lsp_code import (
    CoordinatorBackedLspSessionManager,
    LspCodeBackend,
    LspRepositorySymbol,
    LspSessionManager,
)

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
            project_root=repository.root,
            repository_root=self._attachment_root,
            ensure_ready=lambda: None,
            resolver=resolver or GoplsResolver(),
            supported_extensions=self._GO_EXTENSIONS,
            symbol_kind_by_code=self._SYMBOL_KIND_BY_CODE,
            ignored_directories=self._IGNORED_DIRECTORIES,
            client_factory=client_factory,
            session_manager=session_manager or CoordinatorBackedLspSessionManager(),
        )

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[GoWorkspaceSymbol, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("symbol query must not be empty")
        if "*" in normalized_query or "?" in normalized_query:
            return tuple(
                self._to_go_symbol(item)
                for item in self._backend.get_symbols(normalized_query, is_case_sensitive=is_case_sensitive)
            )
        symbols: list[GoWorkspaceSymbol] = []
        candidate_files = self._iter_exact_query_files(normalized_query, is_case_sensitive)
        if not candidate_files:
            return tuple()
        with self._backend.open_session() as client:
            for attachment_rel_path in candidate_files:
                symbols.extend(
                    self._to_go_symbol(item)
                    for item in self._backend.list_file_symbols_with_client(
                        client,
                        attachment_rel_path,
                        query=normalized_query,
                        is_case_sensitive=is_case_sensitive,
                    )
                )
        return tuple(
            sorted(
                symbols,
                key=lambda item: (
                    item.name,
                    item.repository_rel_path,
                    item.line_start or 0,
                    item.column_start or 0,
                ),
            )
        )

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

    def _iter_exact_query_files(self, query: str, is_case_sensitive: bool) -> tuple[str, ...]:
        files: list[str] = []
        for file_path in self._attachment_root.rglob("*.go"):
            if not file_path.is_file():
                continue
            relative_parts = file_path.relative_to(self._attachment_root).parts[:-1]
            if any(part in self._IGNORED_DIRECTORIES or part.startswith(".") for part in relative_parts):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            candidate_content = content if is_case_sensitive else content.casefold()
            candidate_query = query if is_case_sensitive else query.casefold()
            if candidate_query in candidate_content:
                files.append(file_path.relative_to(self._attachment_root).as_posix())
        return tuple(sorted(files))

    @contextmanager
    def open_session(self):
        with self._backend.open_session() as client:
            yield _GoSymbolSession(self, client)


class _GoSymbolSession:
    def __init__(self, service: _GoSymbolServiceBase, client: LspClient) -> None:
        self._service = service
        self._client = client

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[GoWorkspaceSymbol, ...]:
        return tuple(
            self._service._to_go_symbol(item)
            for item in self._service._backend.list_file_symbols_with_client(
                self._client,
                self._service._to_attachment_rel_path(repository_rel_path),
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._service._rebase_locations(
            self._service._backend.find_definition_with_client(
                self._client,
                self._service._to_attachment_rel_path(repository_rel_path),
                line,
                column,
            )
        )

    def find_implementations(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._service._rebase_locations(
            self._service._backend.find_implementations_with_client(
                self._client,
                self._service._to_attachment_rel_path(repository_rel_path),
                line,
                column,
            )
        )


class GoSymbolService(_GoSymbolServiceBase):
    pass


class GoFileSymbolService(_GoSymbolServiceBase):
    pass
