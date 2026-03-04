from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.core.repository import Repository
from suitcode.providers.npm.symbol_service import NpmFileSymbolService, NpmSymbolService
from suitcode.providers.shared.lsp.messages import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)
from tests.providers.npm.expected_npm_symbol_data import EXPECTED_FILE_SYMBOLS


class _FakeResolver:
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        return ("typescript-language-server", "--stdio", "--tsserver-path", "tsserver")


class _FakeClient:
    def __init__(self, results: tuple[LspWorkspaceSymbol, ...]) -> None:
        self._results = results

    def initialize(self, root_path: Path) -> None:
        return None

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        return self._results

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        return tuple()

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return tuple()

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False) -> tuple[LspLocation, ...]:
        return tuple()

    def shutdown(self) -> None:
        return None

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()


def _symbol(uri: str, name: str = "Core", kind: int = 5) -> LspWorkspaceSymbol:
    return LspWorkspaceSymbol(
        name=name,
        kind=kind,
        container_name="container",
        location=LspLocation(
            uri=uri,
            range=LspRange(
                start=LspPosition(line=0, character=0),
                end=LspPosition(line=10, character=1),
            ),
        ),
    )


class _FakeDocumentClient:
    def __init__(self, results: tuple[LspDocumentSymbol, ...]) -> None:
        self._results = results

    def initialize(self, root_path: Path) -> None:
        return None

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        return self._results

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return tuple()

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False) -> tuple[LspLocation, ...]:
        return tuple()

    def shutdown(self) -> None:
        return None

    def __enter__(self) -> "_FakeDocumentClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()


class _FakeLocationClient:
    def __init__(self, locations: tuple[LspLocation, ...]) -> None:
        self._locations = locations

    def initialize(self, root_path: Path) -> None:
        return None

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return self._locations

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False) -> tuple[LspLocation, ...]:
        return self._locations

    def shutdown(self) -> None:
        return None

    def __enter__(self) -> "_FakeLocationClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()


def _document_symbol(
    name: str,
    kind: int,
    line_start: int,
    line_end: int,
    detail: str | None = None,
    children: tuple[LspDocumentSymbol, ...] = (),
    column_start: int = 1,
    column_end: int = 2,
) -> LspDocumentSymbol:
    return LspDocumentSymbol(
        name=name,
        kind=kind,
        detail=detail,
        range=LspRange(
            start=LspPosition(line=line_start - 1, character=column_start - 1),
            end=LspPosition(line=line_end - 1, character=column_end - 1),
        ),
        selection_range=LspRange(
            start=LspPosition(line=line_start - 1, character=column_start - 1),
            end=LspPosition(line=line_start - 1, character=column_end - 1),
        ),
        children=children,
    )


def _document_symbols_by_path() -> dict[str, tuple[LspDocumentSymbol, ...]]:
    return {
        "apps/admin-portal/src/index.tsx": (
            _document_symbol("AdminPortal", 12, 5, 12, detail="AdminPortal()"),
        ),
        "apps/api-server/src/index.ts": (
            _document_symbol("app", 14, 6, 6, detail="const app"),
        ),
        "apps/web-app/src/index.tsx": (
            _document_symbol("App", 12, 6, 12, detail="App()"),
        ),
        "libs/auth-lib/src/index.ts": (
            _document_symbol("generateToken", 12, 6, 8, detail="generateToken(payload: any): string"),
            _document_symbol("hashPassword", 12, 10, 12, detail="hashPassword(password: string): Promise<string>"),
        ),
        "libs/data-access/src/index.ts": (
            _document_symbol("connectDatabase", 12, 5, 7, detail="connectDatabase(url: string): Promise<void>"),
            _document_symbol("getUserModel", 12, 9, 11, detail="getUserModel()"),
        ),
        "libs/logging-lib/src/index.ts": (
            _document_symbol("logger", 14, 4, 8, detail="const logger"),
        ),
        "libs/metrics-lib/src/index.ts": (
            _document_symbol("register", 14, 4, 4, detail="const register"),
            _document_symbol("createCounter", 12, 6, 11, detail="createCounter(name: string)"),
        ),
        "libs/shared-ui/src/index.tsx": (
            _document_symbol("Button", 12, 4, 6, detail="Button({ label }: { label: string })"),
        ),
        "modules/python-bridge/index.js": tuple(),
        "modules/wasm-module/index.js": tuple(),
        "packages/api-client/src/index.ts": (
            _document_symbol(
                "ApiClient",
                5,
                5,
                16,
                detail="class ApiClient",
                children=(
                    _document_symbol("baseUrl", 7, 6, 6, detail="baseUrl: string", column_start=3, column_end=4),
                    _document_symbol("constructor", 9, 8, 10, detail="constructor(baseUrl: string)", column_start=3, column_end=4),
                    _document_symbol("get", 6, 12, 15, detail="get(endpoint: string): Promise<any>", column_start=3, column_end=4),
                ),
            ),
        ),
        "packages/config/src/index.ts": (
            _document_symbol("Config", 11, 3, 6, detail="interface Config"),
            _document_symbol("loadConfig", 12, 8, 13, detail="loadConfig(): Config"),
        ),
        "packages/core/src/index.test.ts": tuple(),
        "packages/core/src/index.ts": (
            _document_symbol(
                "Core",
                5,
                1,
                13,
                detail="class Core",
                children=(
                    _document_symbol("constructor", 9, 4, 6, detail="constructor(value: string)", column_start=3, column_end=4),
                    _document_symbol("getValue", 6, 8, 10, detail="getValue(): string", column_start=3, column_end=4),
                    _document_symbol("setValue", 6, 12, 14, detail="setValue(value: string): void", column_start=3, column_end=4),
                ),
            ),
        ),
        "packages/data-models/src/index.ts": (
            _document_symbol("User", 11, 3, 6, detail="interface User"),
            _document_symbol("Product", 11, 8, 12, detail="interface Product"),
        ),
        "packages/utils/src/index.test.ts": tuple(),
        "packages/utils/src/index.ts": (
            _document_symbol("formatString", 12, 3, 5, detail="formatString(value: string): string"),
            _document_symbol("processCore", 12, 7, 9, detail="processCore(core: Core): string"),
        ),
        "services/analytics/src/index.ts": (
            _document_symbol(
                "Analytics",
                5,
                4,
                11,
                detail="class Analytics",
                children=(
                    _document_symbol("counter", 7, 5, 5, detail="counter", column_start=3, column_end=4),
                    _document_symbol("track", 6, 7, 10, detail="track(event: string): void", column_start=3, column_end=4),
                ),
            ),
        ),
        "services/auth-service/src/index.ts": (
            _document_symbol(
                "AuthService",
                5,
                5,
                14,
                detail="class AuthService",
                children=(
                    _document_symbol(
                        "authenticate",
                        6,
                        6,
                        13,
                        detail="authenticate(username: string, password: string): Promise<string>",
                        column_start=3,
                        column_end=4,
                    ),
                ),
            ),
        ),
        "services/data-processor/src/index.ts": (
            _document_symbol(
                "DataProcessor",
                5,
                3,
                14,
                detail="class DataProcessor",
                children=(
                    _document_symbol("wasmReady", 7, 4, 4, detail="wasmReady: Promise<void>", column_start=3, column_end=4),
                    _document_symbol("constructor", 9, 6, 8, detail="constructor()", column_start=3, column_end=4),
                    _document_symbol("process", 6, 10, 13, detail="process(data: number[]): Promise<number[]>", column_start=3, column_end=4),
                ),
            ),
        ),
        "services/notification/src/index.ts": (
            _document_symbol(
                "NotificationService",
                5,
                3,
                7,
                detail="class NotificationService",
                children=(
                    _document_symbol("send", 6, 4, 6, detail="send(user: User, message: string): void", column_start=3, column_end=4),
                ),
            ),
        ),
        "tools/build-aggregator/src/index.ts": (
            _document_symbol("buildAll", 12, 3, 5, detail="buildAll()"),
        ),
    }


def test_symbol_service_rejects_empty_query(npm_repository: Repository) -> None:
    service = NpmSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeClient(tuple()),
    )

    with pytest.raises(ValueError, match="symbol query must not be empty"):
        service.get_symbols("  ")


def test_symbol_service_filters_results_to_repository_local_js_ts_files(tmp_path: Path, npm_repository: Repository) -> None:
    inside_ts = (npm_repository.root / "packages" / "core" / "src" / "index.ts").resolve().as_uri()
    outside_py = (tmp_path / "outside.py").resolve().as_uri()
    inside_py = (npm_repository.root / "tools" / "codegen" / "main.py").resolve().as_uri()

    service = NpmSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeClient(
            (
                _symbol(inside_ts, name="Core", kind=5),
                _symbol(outside_py, name="Outside", kind=12),
                _symbol(inside_py, name="Codegen", kind=12),
            )
        ),
    )

    symbols = service.get_symbols("Core")

    assert len(symbols) == 1
    assert symbols[0].name == "Core"
    assert symbols[0].repository_rel_path == "packages/core/src/index.ts"
    assert symbols[0].kind == "class"
    assert symbols[0].line_start == 1
    assert symbols[0].column_start == 1


def test_symbol_service_matches_exact_names_case_insensitively(npm_repository: Repository) -> None:
    inside_ts = (npm_repository.root / "packages" / "core" / "src" / "index.ts").resolve().as_uri()

    service = NpmSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeClient(
            (
                _symbol(inside_ts, name="Core", kind=5),
                _symbol(inside_ts, name="CoreFactory", kind=5),
            )
        ),
    )

    symbols = service.get_symbols("core")

    assert [item.name for item in symbols] == ["Core"]


def test_symbol_service_respects_case_sensitive_flag(npm_repository: Repository) -> None:
    inside_ts = (npm_repository.root / "packages" / "core" / "src" / "index.ts").resolve().as_uri()

    service = NpmSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeClient(
            (
                _symbol(inside_ts, name="Core", kind=5),
            )
        ),
    )

    assert service.get_symbols("core", is_case_sensitive=True) == tuple()
    assert [item.name for item in service.get_symbols("Core", is_case_sensitive=True)] == ["Core"]


def test_symbol_service_uses_glob_matching_when_query_contains_wildcards(npm_repository: Repository) -> None:
    inside_ts = (npm_repository.root / "packages" / "core" / "src" / "index.ts").resolve().as_uri()

    service = NpmSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeClient(
            (
                _symbol(inside_ts, name="Core", kind=5),
                _symbol(inside_ts, name="CoreFactory", kind=5),
            )
        ),
    )

    symbols = service.get_symbols("Core*")

    assert [item.name for item in symbols] == ["Core", "CoreFactory"]


def test_expected_symbol_data_covers_all_fixture_js_ts_sources(npm_fixture_root: Path) -> None:
    actual_files = {
        path.relative_to(npm_fixture_root).as_posix()
        for path in npm_fixture_root.rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    }
    assert set(EXPECTED_FILE_SYMBOLS.keys()) == actual_files
    assert set(_document_symbols_by_path().keys()) == actual_files


@pytest.mark.parametrize(
    ("repository_rel_path", "document_symbols"),
    list(_document_symbols_by_path().items()),
)
def test_file_symbol_service_returns_expected_fixture_entities(
    npm_repository: Repository,
    repository_rel_path: str,
    document_symbols: tuple[LspDocumentSymbol, ...],
) -> None:
    service = NpmFileSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeDocumentClient(document_symbols),
    )

    symbols = service.get_file_entities(repository_rel_path)

    assert [
        {
            "name": symbol.name,
            "kind": symbol.kind,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
            "column_start": symbol.column_start,
            "column_end": symbol.column_end,
            "signature": symbol.signature,
        }
        for symbol in symbols
    ] == list(EXPECTED_FILE_SYMBOLS[repository_rel_path])


def test_file_symbol_service_supports_exact_and_glob_filtering(npm_repository: Repository) -> None:
    document_symbols = _document_symbols_by_path()["packages/core/src/index.ts"]
    service = NpmFileSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeDocumentClient(document_symbols),
    )

    exact = service.list_file_symbols("packages/core/src/index.ts", query="Core")
    globbed = service.list_file_symbols("packages/core/src/index.ts", query="*Value")

    assert [item.name for item in exact] == ["Core"]
    assert [item.name for item in globbed] == ["getValue", "setValue"]


def test_file_symbol_service_definition_and_references_translate_locations(npm_repository: Repository) -> None:
    location = LspLocation(
        uri='file:///c%3A'
        + (npm_repository.root / "packages" / "core" / "src" / "index.ts")
        .resolve()
        .as_posix()
        .removeprefix('C:'),
        range=LspRange(
            start=LspPosition(line=6, character=2),
            end=LspPosition(line=6, character=8),
        ),
    )
    service = NpmFileSymbolService(
        npm_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeLocationClient((location,)),
    )

    definition = service.find_definition("packages/core/src/index.ts", 7, 3)
    references = service.find_references("packages/core/src/index.ts", 7, 3, include_definition=True)

    assert definition == (("packages/core/src/index.ts", 7, 7, 3, 9),)
    assert references == definition
