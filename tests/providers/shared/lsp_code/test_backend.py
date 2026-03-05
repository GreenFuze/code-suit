from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from suitcode.providers.shared.lsp import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)
from suitcode.providers.shared.lsp_code.backend import LspCodeBackend


class _FakeResolver:
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        return ("fake-lsp", "--stdio")


class _FakeClient:
    def __init__(
        self,
        *,
        workspace_symbols: tuple[LspWorkspaceSymbol, ...] = tuple(),
        document_symbols_by_path: dict[str, tuple[LspDocumentSymbol, ...]] | None = None,
        definition_locations: tuple[LspLocation, ...] = tuple(),
        reference_locations: tuple[LspLocation, ...] = tuple(),
    ) -> None:
        self.workspace_symbols = workspace_symbols
        self.document_symbols_by_path = document_symbols_by_path or {}
        self.definition_locations = definition_locations
        self.reference_locations = reference_locations
        self.initialized_with: Path | None = None

    def initialize(self, root_path: Path) -> None:
        self.initialized_with = root_path

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        return self.workspace_symbols

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        return self.document_symbols_by_path.get(file_path.as_posix().replace("\\", "/"), tuple())

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return self.definition_locations

    def references(
        self,
        file_path: Path,
        line: int,
        column: int,
        include_declaration: bool = False,
    ) -> tuple[LspLocation, ...]:
        return self.reference_locations

    def shutdown(self) -> None:
        return None


class _FakeSessionManager:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client

    @contextmanager
    def open_client(self, repository_root: Path, resolver, client_factory):
        yield self.client


def _workspace_symbol(uri: str, *, name: str = "Core", kind: int = 5) -> LspWorkspaceSymbol:
    return LspWorkspaceSymbol(
        name=name,
        kind=kind,
        container_name=None,
        location=LspLocation(
            uri=uri,
            range=LspRange(
                start=LspPosition(line=0, character=0),
                end=LspPosition(line=5, character=1),
            ),
        ),
    )


def _document_symbol(name: str, kind: int = 12) -> LspDocumentSymbol:
    return LspDocumentSymbol(
        name=name,
        kind=kind,
        detail=None,
        range=LspRange(
            start=LspPosition(line=0, character=0),
            end=LspPosition(line=0, character=5),
        ),
        selection_range=LspRange(
            start=LspPosition(line=0, character=0),
            end=LspPosition(line=0, character=5),
        ),
        children=tuple(),
    )


def test_backend_get_symbols_keeps_exact_and_glob_matching(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "a.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("x = 1\n", encoding="utf-8")
    client = _FakeClient(
        workspace_symbols=(
            _workspace_symbol(src_file.resolve().as_uri(), name="Core"),
            _workspace_symbol(src_file.resolve().as_uri(), name="CoreFactory"),
        )
    )
    backend = LspCodeBackend(
        repository_root=tmp_path,
        ensure_ready=lambda: None,
        resolver=_FakeResolver(),
        supported_extensions=frozenset({".py"}),
        symbol_kind_by_code={5: "class"},
        ignored_directories=frozenset({".git"}),
        session_manager=_FakeSessionManager(client),
    )

    exact = backend.get_symbols("core")
    globbed = backend.get_symbols("Core*")

    assert [item.name for item in exact] == ["Core"]
    assert [item.name for item in globbed] == ["Core", "CoreFactory"]


def test_backend_falls_back_to_document_symbols_when_workspace_symbol_is_empty(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "fallback.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("def build_repository_id():\n    return 'x'\n", encoding="utf-8")
    key = src_file.resolve().as_posix().replace("\\", "/")
    client = _FakeClient(
        workspace_symbols=tuple(),
        document_symbols_by_path={key: (_document_symbol("build_repository_id"),)},
    )
    backend = LspCodeBackend(
        repository_root=tmp_path,
        ensure_ready=lambda: None,
        resolver=_FakeResolver(),
        supported_extensions=frozenset({".py"}),
        symbol_kind_by_code={12: "function"},
        ignored_directories=frozenset({".git"}),
        session_manager=_FakeSessionManager(client),
    )

    symbols = backend.get_symbols("build_repository_id")

    assert [item.name for item in symbols] == ["build_repository_id"]
    assert symbols[0].repository_rel_path == "src/fallback.py"


def test_backend_list_file_symbols_validates_paths_and_ignores_unsupported_extension(tmp_path: Path) -> None:
    py_file = tmp_path / "ok.py"
    txt_file = tmp_path / "note.txt"
    py_file.write_text("def f():\n    pass\n", encoding="utf-8")
    txt_file.write_text("hello\n", encoding="utf-8")
    key = py_file.resolve().as_posix().replace("\\", "/")
    client = _FakeClient(document_symbols_by_path={key: (_document_symbol("f"),)})
    backend = LspCodeBackend(
        repository_root=tmp_path,
        ensure_ready=lambda: None,
        resolver=_FakeResolver(),
        supported_extensions=frozenset({".py"}),
        symbol_kind_by_code={12: "function"},
        ignored_directories=frozenset({".git"}),
        session_manager=_FakeSessionManager(client),
    )

    assert [item.name for item in backend.list_file_symbols("ok.py")] == ["f"]
    assert backend.list_file_symbols("note.txt") == tuple()
    with pytest.raises(ValueError, match="escapes repository root"):
        backend.list_file_symbols("../outside.py")


def test_backend_translates_definition_and_reference_locations(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "main.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("value = 1\n", encoding="utf-8")
    location = LspLocation(
        uri=src_file.resolve().as_uri(),
        range=LspRange(
            start=LspPosition(line=3, character=1),
            end=LspPosition(line=3, character=5),
        ),
    )
    client = _FakeClient(
        definition_locations=(location,),
        reference_locations=(location,),
    )
    backend = LspCodeBackend(
        repository_root=tmp_path,
        ensure_ready=lambda: None,
        resolver=_FakeResolver(),
        supported_extensions=frozenset({".py"}),
        symbol_kind_by_code={12: "function"},
        ignored_directories=frozenset({".git"}),
        session_manager=_FakeSessionManager(client),
    )

    assert backend.find_definition("src/main.py", 1, 1) == (("src/main.py", 4, 4, 2, 6),)
    assert backend.find_references("src/main.py", 1, 1, include_definition=True) == (
        ("src/main.py", 4, 4, 2, 6),
    )
