from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from suitcode.providers.python.lsp_resolution import BasedPyrightResolver
from suitcode.providers.python.symbol_models import PythonSymbolQuery, PythonWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient, LspDocumentSymbol, LspLocation, LspWorkspaceSymbol
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class _PythonSymbolServiceBase:
    _PYTHON_EXTENSIONS = frozenset({'.py'})
    _SYMBOL_KIND_BY_CODE = {
        1: 'file',
        2: 'module',
        3: 'namespace',
        4: 'package',
        5: 'class',
        6: 'method',
        7: 'property',
        8: 'field',
        9: 'constructor',
        10: 'enum',
        11: 'interface',
        12: 'function',
        13: 'variable',
        14: 'constant',
        23: 'struct',
        26: 'type-parameter',
    }

    def __init__(
        self,
        repository: Repository,
        manifest_loader: PyProjectWorkspaceLoader | None = None,
        resolver: BasedPyrightResolver | None = None,
        client_factory: Callable[[tuple[str, ...], Path], LspClient] | None = None,
    ) -> None:
        self._repository = repository
        self._manifest_loader = manifest_loader or PyProjectWorkspaceLoader()
        self._resolver = resolver or BasedPyrightResolver()
        self._client_factory = client_factory or (lambda command, cwd: LspClient(command, cwd))

    def _validate_query(self, query: str) -> PythonSymbolQuery:
        normalized = query.strip()
        if not normalized:
            raise ValueError('symbol query must not be empty')
        return PythonSymbolQuery(query=normalized)

    def _workspace_query(self, query: str) -> str:
        collapsed = query.replace('*', '').replace('?', '').strip()
        return collapsed or query

    def _matches_query(self, symbol_name: str, query: str, is_case_sensitive: bool) -> bool:
        candidate_name = symbol_name if is_case_sensitive else symbol_name.casefold()
        candidate_query = query if is_case_sensitive else query.casefold()
        if '*' in query or '?' in query:
            return fnmatchcase(candidate_name, candidate_query)
        return candidate_name == candidate_query

    def _filter_symbols(
        self,
        symbols: tuple[PythonWorkspaceSymbol, ...],
        query: str,
        is_case_sensitive: bool,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        return tuple(symbol for symbol in symbols if self._matches_query(symbol.name, query, is_case_sensitive))

    def _ensure_manifest(self) -> None:
        self._manifest_loader.load(self._repository.root)

    def _build_client(self) -> LspClient:
        command = self._resolver.resolve(self._repository.root)
        return self._client_factory(command, self._repository.root)

    def _symbol_kind(self, kind: int) -> str:
        return self._SYMBOL_KIND_BY_CODE.get(kind, 'unknown')

    def _path_from_uri(self, uri: str) -> Path | None:
        parsed = urlparse(uri)
        if parsed.scheme != 'file':
            return None
        resolved = Path(url2pathname(unquote(parsed.path))).resolve()
        try:
            resolved.relative_to(self._repository.root)
        except ValueError:
            return None
        return resolved

    def _validate_repository_file(self, repository_rel_path: str) -> Path:
        normalized = repository_rel_path.strip().replace('\\', '/').removeprefix('./')
        if not normalized:
            raise ValueError('repository_rel_path must not be empty')
        file_path = (self._repository.root / normalized).resolve()
        try:
            file_path.relative_to(self._repository.root)
        except ValueError as exc:
            raise ValueError(f'path escapes repository root: `{repository_rel_path}`') from exc
        if not file_path.exists():
            raise ValueError(f'file does not exist: `{repository_rel_path}`')
        if not file_path.is_file():
            raise ValueError(f'path is not a file: `{repository_rel_path}`')
        return file_path

    def _is_supported_symbol_file(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self._PYTHON_EXTENSIONS

    @staticmethod
    def _validate_position(line: int, column: int) -> None:
        if line < 1 or column < 1:
            raise ValueError('line and column must be >= 1')

    def _translate_locations(self, locations: tuple[LspLocation, ...]) -> tuple[tuple[str, int, int, int, int], ...]:
        translated: list[tuple[str, int, int, int, int]] = []
        for location in locations:
            file_path = self._path_from_uri(location.uri)
            if file_path is None or not self._is_supported_symbol_file(file_path):
                continue
            location_range = location.range
            translated.append(
                (
                    file_path.relative_to(self._repository.root).as_posix(),
                    location_range.start.line + 1,
                    location_range.end.line + 1,
                    location_range.start.character + 1,
                    location_range.end.character + 1,
                )
            )
        return tuple(translated)


class PythonSymbolService(_PythonSymbolServiceBase):
    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[PythonWorkspaceSymbol, ...]:
        symbol_query = self._validate_query(query)
        self._ensure_manifest()
        with self._build_client() as client:
            client.initialize(self._repository.root)
            results = client.workspace_symbol(self._workspace_query(symbol_query.query))
            translated = tuple(item for item in (self._translate_symbol(result) for result in results) if item is not None)
            filtered = self._filter_symbols(translated, symbol_query.query, is_case_sensitive)
            if filtered:
                return tuple(sorted(filtered, key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0)))
            fallback = self._fallback_symbols(client, symbol_query.query, is_case_sensitive)
        return tuple(sorted(fallback, key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0)))

    def _translate_symbol(self, symbol: LspWorkspaceSymbol) -> PythonWorkspaceSymbol | None:
        if symbol.location is None:
            return None
        file_path = self._path_from_uri(symbol.location.uri)
        if file_path is None or file_path.suffix.lower() not in self._PYTHON_EXTENSIONS:
            return None
        symbol_range = symbol.location.range
        return PythonWorkspaceSymbol(
            name=symbol.name,
            kind=self._symbol_kind(symbol.kind),
            repository_rel_path=file_path.relative_to(self._repository.root).as_posix(),
            line_start=symbol_range.start.line + 1,
            line_end=symbol_range.end.line + 1,
            column_start=symbol_range.start.character + 1,
            column_end=symbol_range.end.character + 1,
            container_name=symbol.container_name,
            signature=symbol.container_name,
        )

    def _fallback_symbols(self, client: LspClient, query: str, is_case_sensitive: bool) -> tuple[PythonWorkspaceSymbol, ...]:
        matches: list[PythonWorkspaceSymbol] = []
        for file_path in self._iter_python_files():
            repository_rel_path = file_path.relative_to(self._repository.root).as_posix()
            symbols = client.document_symbol(file_path)
            flattened = self._flatten_symbols(symbols, repository_rel_path, None)
            for symbol in flattened:
                if self._matches_query(symbol.name, query, is_case_sensitive):
                    matches.append(symbol)
        return tuple(matches)

    def _iter_python_files(self) -> tuple[Path, ...]:
        ignored = {'__pycache__', '.git', '.venv', 'venv', 'env', '.mypy_cache', '.pytest_cache', 'node_modules'}
        files: list[Path] = []
        for file_path in self._repository.root.rglob('*.py'):
            relative_parts = file_path.relative_to(self._repository.root).parts[:-1]
            if any(part in ignored or part.startswith('.') for part in relative_parts):
                continue
            files.append(file_path)
        return tuple(sorted(files))

    def _flatten_symbols(
        self,
        symbols: tuple[LspDocumentSymbol, ...],
        repository_rel_path: str,
        container_name: str | None,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        flattened: list[PythonWorkspaceSymbol] = []
        for symbol in symbols:
            current_container_name = container_name or symbol.container_name
            flattened.append(
                PythonWorkspaceSymbol(
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


class PythonFileSymbolService(_PythonSymbolServiceBase):
    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        file_path = self._validate_repository_file(repository_rel_path)
        if not self._is_supported_symbol_file(file_path):
            return tuple()
        self._ensure_manifest()
        with self._build_client() as client:
            client.initialize(self._repository.root)
            results = client.document_symbol(file_path)
        flattened = self._flatten_symbols(results, file_path.relative_to(self._repository.root).as_posix(), None)
        if query is not None:
            normalized_query = self._validate_query(query).query
            flattened = self._filter_symbols(flattened, normalized_query, is_case_sensitive)
        return tuple(sorted(flattened, key=lambda item: (item.name, item.kind, item.line_start or 0, item.column_start or 0)))

    def get_file_symbols(self, repository_rel_path: str) -> tuple[PythonWorkspaceSymbol, ...]:
        return self.list_file_symbols(repository_rel_path)

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        self._validate_position(line, column)
        file_path = self._validate_repository_file(repository_rel_path)
        if not self._is_supported_symbol_file(file_path):
            return tuple()
        self._ensure_manifest()
        with self._build_client() as client:
            client.initialize(self._repository.root)
            return self._translate_locations(client.definition(file_path, line, column))

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
        self._ensure_manifest()
        with self._build_client() as client:
            client.initialize(self._repository.root)
            return self._translate_locations(client.references(file_path, line, column, include_declaration=include_definition))

    def _flatten_symbols(
        self,
        symbols: tuple[LspDocumentSymbol, ...],
        repository_rel_path: str,
        container_name: str | None,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        flattened: list[PythonWorkspaceSymbol] = []
        for symbol in symbols:
            current_container_name = container_name or symbol.container_name
            flattened.append(
                PythonWorkspaceSymbol(
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
