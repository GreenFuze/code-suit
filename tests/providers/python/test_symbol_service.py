from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.providers.python.lsp_resolution import BasedPyrightResolver
from suitcode.providers.python.symbol_service import PythonFileSymbolService, PythonSymbolService
from suitcode.providers.shared.lsp.messages import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)
from tests.providers.python.expected_python_symbol_data import EXPECTED_FILE_SYMBOLS


class _FakeResolver:
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        return ('basedpyright-langserver', '--stdio')


class _FakeWorkspaceClient:
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()




class _FallbackClient:
    def __init__(self, document_symbols_by_path: dict[str, tuple[LspDocumentSymbol, ...]]) -> None:
        self._document_symbols_by_path = document_symbols_by_path

    def initialize(self, root_path: Path) -> None:
        return None

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        return tuple()

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        key = file_path.as_posix().replace('\\', '/')
        return self._document_symbols_by_path.get(key, tuple())

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return tuple()

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False) -> tuple[LspLocation, ...]:
        return tuple()

    def shutdown(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

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

    def __enter__(self):
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()


def _workspace_symbol(uri: str, name: str = 'RepositoryManager', kind: int = 5) -> LspWorkspaceSymbol:
    return LspWorkspaceSymbol(
        name=name,
        kind=kind,
        container_name='container',
        location=LspLocation(
            uri=uri,
            range=LspRange(
                start=LspPosition(line=0, character=0),
                end=LspPosition(line=6, character=10),
            ),
        ),
    )


def _document_symbol(name: str, kind: int, line_start: int, line_end: int, detail: str | None = None, children: tuple[LspDocumentSymbol, ...] = (), column_start: int = 1, column_end: int = 10) -> LspDocumentSymbol:
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
        'src/acme/__init__.py': tuple(),
        'src/acme/core/__init__.py': tuple(),
        'src/acme/core/models/__init__.py': tuple(),
        'src/acme/core/repository.py': (
            _document_symbol(
                'RepositoryManager',
                5,
                1,
                7,
                children=(
                    _document_symbol('__init__', 9, 2, 3, detail='__init__(prefix: str)', column_start=5, column_end=15),
                    _document_symbol('build', 6, 5, 6, detail='build(name: str) -> str', column_start=5, column_end=10),
                ),
            ),
            _document_symbol('build_repository_id', 12, 9, 11, detail='build_repository_id(name: str) -> str'),
        ),
        'src/acme/mcp/__init__.py': tuple(),
        'src/acme/mcp/server.py': (
            _document_symbol('run_server', 12, 1, 2, detail='run_server() -> str'),
            _document_symbol('main', 12, 5, 6, detail='main() -> str'),
        ),
        'src/acme/providers/__init__.py': tuple(),
        'src/acme/providers/python/__init__.py': (
            _document_symbol('cli', 12, 1, 2, detail='cli() -> str'),
        ),
        'tests/test_basic.py': (
            _document_symbol('test_smoke', 12, 1, 2, detail='test_smoke() -> None'),
        ),
        'tests_unittest/test_unittest_sample.py': (
            _document_symbol(
                'SampleTest',
                5,
                4,
                6,
                children=(
                    _document_symbol('test_truth', 6, 5, 6, detail='test_truth() -> None', column_start=5, column_end=14),
                ),
            ),
        ),
    }


def test_basedpyright_resolver_prefers_local_virtualenv(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    executable = repo_root / '.venv' / 'Scripts' / 'basedpyright-langserver.cmd'
    executable.parent.mkdir(parents=True)
    executable.write_text('@echo off\r\n', encoding='utf-8')

    resolved = BasedPyrightResolver().resolve(repo_root)

    assert resolved[0] == str(executable.resolve())
    assert resolved[1:] == ('--stdio',)


def test_symbol_service_rejects_empty_query(python_repository) -> None:
    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeWorkspaceClient(tuple()),
    )

    with pytest.raises(ValueError, match='symbol query must not be empty'):
        service.get_symbols('   ')


def test_symbol_service_filters_results_to_repository_local_python_files(tmp_path: Path, python_repository) -> None:
    inside_py = (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py').resolve().as_uri()
    outside_py = (tmp_path / 'outside.py').resolve().as_uri()
    inside_txt = (python_repository.root / 'README.txt').resolve().as_uri()

    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeWorkspaceClient(
            (
                _workspace_symbol(inside_py),
                _workspace_symbol(outside_py, name='Outside', kind=12),
                _workspace_symbol(inside_txt, name='Text', kind=12),
            )
        ),
    )

    symbols = service.get_symbols('RepositoryManager')

    assert len(symbols) == 1
    assert symbols[0].name == 'RepositoryManager'
    assert symbols[0].repository_rel_path == 'src/acme/core/repository.py'
    assert symbols[0].kind == 'class'


def test_symbol_service_matches_exact_names_case_insensitively(python_repository) -> None:
    inside_py = (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py').resolve().as_uri()

    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeWorkspaceClient(
            (
                _workspace_symbol(inside_py, name='RepositoryManager', kind=5),
                _workspace_symbol(inside_py, name='RepositoryManagerFactory', kind=5),
            )
        ),
    )

    symbols = service.get_symbols('repositorymanager')

    assert [item.name for item in symbols] == ['RepositoryManager']


def test_symbol_service_respects_case_sensitive_flag(python_repository) -> None:
    inside_py = (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py').resolve().as_uri()

    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeWorkspaceClient(
            (
                _workspace_symbol(inside_py, name='RepositoryManager', kind=5),
            )
        ),
    )

    assert service.get_symbols('repositorymanager', is_case_sensitive=True) == tuple()
    assert [item.name for item in service.get_symbols('RepositoryManager', is_case_sensitive=True)] == ['RepositoryManager']


def test_symbol_service_falls_back_to_document_symbols_when_workspace_symbol_is_empty(python_repository) -> None:
    document_symbols_by_path = {
        (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py').as_posix().replace('\\', '/'): _document_symbols_by_path()['src/acme/core/repository.py'],
    }
    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FallbackClient(document_symbols_by_path),
    )

    symbols = service.get_symbols('RepositoryManager')

    assert [item.name for item in symbols] == ['RepositoryManager']


def test_symbol_service_uses_glob_matching_when_query_contains_wildcards(python_repository) -> None:
    document_symbols_by_path = {
        (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py').as_posix().replace('\\', '/'): _document_symbols_by_path()['src/acme/core/repository.py'],
    }
    service = PythonSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FallbackClient(document_symbols_by_path),
    )

    symbols = service.get_symbols('*Repository*')

    assert [item.name for item in symbols] == ['RepositoryManager', 'build_repository_id']

def test_expected_symbol_data_covers_all_fixture_python_sources(python_fixture_root) -> None:
    actual_files = {path.relative_to(python_fixture_root).as_posix() for path in python_fixture_root.rglob('*.py')}
    assert set(EXPECTED_FILE_SYMBOLS.keys()) == actual_files
    assert set(_document_symbols_by_path().keys()) == actual_files


@pytest.mark.parametrize(('repository_rel_path', 'document_symbols'), list(_document_symbols_by_path().items()))
def test_file_symbol_service_returns_expected_fixture_entities(python_repository, repository_rel_path: str, document_symbols: tuple[LspDocumentSymbol, ...]) -> None:
    service = PythonFileSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeDocumentClient(document_symbols),
    )

    symbols = service.get_file_symbols(repository_rel_path)

    assert [
        {
            'name': symbol.name,
            'kind': symbol.kind,
            'line_start': symbol.line_start,
            'line_end': symbol.line_end,
            'column_start': symbol.column_start,
            'column_end': symbol.column_end,
            'signature': symbol.signature,
        }
        for symbol in symbols
    ] == list(EXPECTED_FILE_SYMBOLS[repository_rel_path])


def test_file_symbol_service_supports_exact_and_glob_filtering(python_repository) -> None:
    document_symbols = _document_symbols_by_path()['src/acme/core/repository.py']
    service = PythonFileSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeDocumentClient(document_symbols),
    )

    exact = service.list_file_symbols('src/acme/core/repository.py', query='RepositoryManager')
    globbed = service.list_file_symbols('src/acme/core/repository.py', query='build*')

    assert [item.name for item in exact] == ['RepositoryManager']
    assert [item.name for item in globbed] == ['build', 'build_repository_id']


def test_file_symbol_service_definition_and_references_translate_locations(python_repository) -> None:
    location = LspLocation(
        uri='file:///c%3A'
        + (python_repository.root / 'src' / 'acme' / 'core' / 'repository.py')
        .resolve()
        .as_posix()
        .removeprefix('C:'),
        range=LspRange(
            start=LspPosition(line=4, character=2),
            end=LspPosition(line=4, character=7),
        ),
    )
    service = PythonFileSymbolService(
        python_repository,
        resolver=_FakeResolver(),
        client_factory=lambda command, cwd: _FakeLocationClient((location,)),
    )

    definition = service.find_definition('src/acme/core/repository.py', 5, 3)
    references = service.find_references('src/acme/core/repository.py', 5, 3, include_definition=True)

    assert definition == (('src/acme/core/repository.py', 5, 5, 3, 8),)
    assert references == definition

