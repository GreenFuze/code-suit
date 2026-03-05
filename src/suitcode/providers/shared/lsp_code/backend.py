from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from suitcode.providers.shared.lsp import LspClient, LspDocumentSymbol, LspLocation, LspWorkspaceSymbol
from suitcode.providers.shared.lsp_code.session import (
    LspClientFactory,
    LspResolver,
    LspSessionManager,
    PerCallLspSessionManager,
)


@dataclass(frozen=True)
class LspRepositorySymbol:
    name: str
    kind: str
    repository_rel_path: str
    line_start: int | None
    line_end: int | None
    column_start: int | None
    column_end: int | None
    container_name: str | None
    signature: str | None


class LspCodeBackend:
    def __init__(
        self,
        *,
        repository_root: Path,
        ensure_ready: Callable[[], None],
        resolver: LspResolver,
        supported_extensions: frozenset[str],
        symbol_kind_by_code: Mapping[int, str],
        ignored_directories: frozenset[str],
        client_factory: LspClientFactory | None = None,
        session_manager: LspSessionManager | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._ensure_ready = ensure_ready
        self._resolver = resolver
        self._supported_extensions = supported_extensions
        self._symbol_kind_by_code = dict(symbol_kind_by_code)
        self._ignored_directories = ignored_directories
        self._client_factory = client_factory or (
            lambda command, cwd, initialization_options=None: LspClient(
                command,
                cwd,
                initialization_options=initialization_options,
            )
        )
        self._session_manager = session_manager or PerCallLspSessionManager()

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[LspRepositorySymbol, ...]:
        normalized_query = self._validate_query(query)
        self._ensure_ready()
        with self._session_manager.open_client(self._repository_root, self._resolver, self._client_factory) as client:
            client.initialize(self._repository_root)
            raw = client.workspace_symbol(self._workspace_query(normalized_query))
            translated = tuple(
                item
                for item in (self._translate_workspace_symbol(symbol) for symbol in raw)
                if item is not None
            )
            filtered = self._filter_symbols(translated, normalized_query, is_case_sensitive)
            if filtered:
                return tuple(
                    sorted(
                        filtered,
                        key=lambda item: (
                            item.name,
                            item.repository_rel_path,
                            item.line_start or 0,
                            item.column_start or 0,
                        ),
                    )
                )
            fallback = self._fallback_symbols(client, normalized_query, is_case_sensitive)
        return tuple(
            sorted(
                fallback,
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
    ) -> tuple[LspRepositorySymbol, ...]:
        file_path = self._validate_repository_file(repository_rel_path)
        if not self._is_supported_symbol_file(file_path):
            return tuple()
        self._ensure_ready()
        with self._session_manager.open_client(self._repository_root, self._resolver, self._client_factory) as client:
            client.initialize(self._repository_root)
            raw = client.document_symbol(file_path)
        flattened = self._flatten_symbols(raw, file_path.relative_to(self._repository_root).as_posix(), None)
        if query is not None:
            normalized_query = self._validate_query(query)
            flattened = self._filter_symbols(flattened, normalized_query, is_case_sensitive)
        return tuple(
            sorted(
                flattened,
                key=lambda item: (
                    item.name,
                    item.kind,
                    item.line_start or 0,
                    item.column_start or 0,
                ),
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        self._validate_position(line, column)
        file_path = self._validate_repository_file(repository_rel_path)
        if not self._is_supported_symbol_file(file_path):
            return tuple()
        self._ensure_ready()
        with self._session_manager.open_client(self._repository_root, self._resolver, self._client_factory) as client:
            client.initialize(self._repository_root)
            locations = client.definition(file_path, line, column)
        return self._translate_locations(locations)

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        self._validate_position(line, column)
        file_path = self._validate_repository_file(repository_rel_path)
        if not self._is_supported_symbol_file(file_path):
            return tuple()
        self._ensure_ready()
        with self._session_manager.open_client(self._repository_root, self._resolver, self._client_factory) as client:
            client.initialize(self._repository_root)
            locations = client.references(file_path, line, column, include_declaration=include_definition)
        return self._translate_locations(locations)

    def _validate_query(self, query: str) -> str:
        normalized = query.strip()
        if not normalized:
            raise ValueError("symbol query must not be empty")
        return normalized

    @staticmethod
    def _workspace_query(query: str) -> str:
        collapsed = query.replace("*", "").replace("?", "").strip()
        return collapsed or query

    @staticmethod
    def _matches_query(symbol_name: str, query: str, is_case_sensitive: bool) -> bool:
        candidate_name = symbol_name if is_case_sensitive else symbol_name.casefold()
        candidate_query = query if is_case_sensitive else query.casefold()
        if "*" in query or "?" in query:
            return fnmatchcase(candidate_name, candidate_query)
        return candidate_name == candidate_query

    def _filter_symbols(
        self,
        symbols: tuple[LspRepositorySymbol, ...],
        query: str,
        is_case_sensitive: bool,
    ) -> tuple[LspRepositorySymbol, ...]:
        return tuple(item for item in symbols if self._matches_query(item.name, query, is_case_sensitive))

    def _symbol_kind(self, kind: int) -> str:
        return self._symbol_kind_by_code.get(kind, "unknown")

    def _path_from_uri(self, uri: str) -> Path | None:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        resolved = Path(url2pathname(unquote(parsed.path))).resolve()
        try:
            resolved.relative_to(self._repository_root)
        except ValueError:
            return None
        return resolved

    def _validate_repository_file(self, repository_rel_path: str) -> Path:
        normalized = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
        if not normalized:
            raise ValueError("repository_rel_path must not be empty")
        file_path = (self._repository_root / normalized).resolve()
        try:
            file_path.relative_to(self._repository_root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository root: `{repository_rel_path}`") from exc
        if not file_path.exists():
            raise ValueError(f"file does not exist: `{repository_rel_path}`")
        if not file_path.is_file():
            raise ValueError(f"path is not a file: `{repository_rel_path}`")
        return file_path

    def _is_supported_symbol_file(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self._supported_extensions

    @staticmethod
    def _validate_position(line: int, column: int) -> None:
        if line < 1 or column < 1:
            raise ValueError("line and column must be >= 1")

    def _translate_workspace_symbol(self, symbol: LspWorkspaceSymbol) -> LspRepositorySymbol | None:
        if symbol.location is None:
            return None
        file_path = self._path_from_uri(symbol.location.uri)
        if file_path is None or not self._is_supported_symbol_file(file_path):
            return None
        symbol_range = symbol.location.range
        return LspRepositorySymbol(
            name=symbol.name,
            kind=self._symbol_kind(symbol.kind),
            repository_rel_path=file_path.relative_to(self._repository_root).as_posix(),
            line_start=symbol_range.start.line + 1,
            line_end=symbol_range.end.line + 1,
            column_start=symbol_range.start.character + 1,
            column_end=symbol_range.end.character + 1,
            container_name=symbol.container_name,
            signature=symbol.container_name,
        )

    def _fallback_symbols(self, client, query: str, is_case_sensitive: bool) -> tuple[LspRepositorySymbol, ...]:
        matches: list[LspRepositorySymbol] = []
        for file_path in self._iter_symbol_files():
            repository_rel_path = file_path.relative_to(self._repository_root).as_posix()
            raw = client.document_symbol(file_path)
            flattened = self._flatten_symbols(raw, repository_rel_path, None)
            for symbol in flattened:
                if self._matches_query(symbol.name, query, is_case_sensitive):
                    matches.append(symbol)
        return tuple(matches)

    def _iter_symbol_files(self) -> tuple[Path, ...]:
        files: list[Path] = []
        for extension in self._supported_extensions:
            for file_path in self._repository_root.rglob(f"*{extension}"):
                relative_parts = file_path.relative_to(self._repository_root).parts[:-1]
                if any(part in self._ignored_directories or part.startswith(".") for part in relative_parts):
                    continue
                files.append(file_path)
        return tuple(sorted(set(files)))

    def _flatten_symbols(
        self,
        symbols: tuple[LspDocumentSymbol, ...],
        repository_rel_path: str,
        container_name: str | None,
    ) -> tuple[LspRepositorySymbol, ...]:
        flattened: list[LspRepositorySymbol] = []
        for symbol in symbols:
            current_container_name = container_name or symbol.container_name
            flattened.append(
                LspRepositorySymbol(
                    name=symbol.name,
                    kind=self._symbol_kind(symbol.kind),
                    repository_rel_path=repository_rel_path,
                    line_start=symbol.range.start.line + 1,
                    line_end=symbol.range.end.line + 1,
                    column_start=symbol.range.start.character + 1,
                    column_end=symbol.range.end.character + 1,
                    container_name=current_container_name,
                    signature=symbol.detail or current_container_name,
                )
            )
            flattened.extend(self._flatten_symbols(symbol.children, repository_rel_path, symbol.name))
        return tuple(flattened)

    def _translate_locations(self, locations: tuple[LspLocation, ...]) -> tuple[tuple[str, int, int, int, int], ...]:
        translated: list[tuple[str, int, int, int, int]] = []
        for location in locations:
            file_path = self._path_from_uri(location.uri)
            if file_path is None or not self._is_supported_symbol_file(file_path):
                continue
            location_range = location.range
            translated.append(
                (
                    file_path.relative_to(self._repository_root).as_posix(),
                    location_range.start.line + 1,
                    location_range.end.line + 1,
                    location_range.start.character + 1,
                    location_range.end.character + 1,
                )
            )
        return tuple(translated)
