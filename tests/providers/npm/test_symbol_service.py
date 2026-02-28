from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.core.repository import Repository
from suitcode.providers.npm.symbol_service import NpmSymbolService
from suitcode.providers.shared.lsp.messages import LspLocation, LspPosition, LspRange, LspWorkspaceSymbol


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
