from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from suitcode.providers.python.lsp_resolution import BasedPyrightResolver
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient
from suitcode.providers.shared.lsp_code import LspCodeBackend, LspRepositorySymbol, LspSessionManager
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class _PythonSymbolServiceBase:
    _PYTHON_EXTENSIONS = frozenset({".py"})
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
        26: "type-parameter",
    }
    _IGNORED_DIRECTORIES = frozenset(
        {"__pycache__", ".git", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache", "node_modules"}
    )

    def __init__(
        self,
        repository: Repository,
        manifest_loader: PyProjectWorkspaceLoader | None = None,
        resolver: BasedPyrightResolver | None = None,
        client_factory: Callable[..., LspClient] | None = None,
        session_manager: LspSessionManager | None = None,
    ) -> None:
        self._repository = repository
        self._manifest_loader = manifest_loader or PyProjectWorkspaceLoader()
        self._resolver = resolver or BasedPyrightResolver()
        self._backend = LspCodeBackend(
            repository_root=repository.root,
            ensure_ready=self._ensure_manifest,
            resolver=self._resolver,
            supported_extensions=self._PYTHON_EXTENSIONS,
            symbol_kind_by_code=self._SYMBOL_KIND_BY_CODE,
            ignored_directories=self._IGNORED_DIRECTORIES,
            client_factory=client_factory,
            session_manager=session_manager,
        )

    def _ensure_manifest(self) -> None:
        self._manifest_loader.load(self._repository.root)

    @staticmethod
    def _to_python_symbol(symbol: LspRepositorySymbol) -> PythonWorkspaceSymbol:
        return PythonWorkspaceSymbol(
            name=symbol.name,
            kind=symbol.kind,
            repository_rel_path=symbol.repository_rel_path,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            column_start=symbol.column_start,
            column_end=symbol.column_end,
            container_name=symbol.container_name,
            signature=symbol.signature,
        )


class PythonSymbolService(_PythonSymbolServiceBase):
    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[PythonWorkspaceSymbol, ...]:
        return tuple(
            self._to_python_symbol(item)
            for item in self._backend.get_symbols(query, is_case_sensitive=is_case_sensitive)
        )


class PythonFileSymbolService(_PythonSymbolServiceBase):
    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        return tuple(
            self._to_python_symbol(item)
            for item in self._backend.list_file_symbols(
                repository_rel_path,
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        )

    def get_file_symbols(self, repository_rel_path: str) -> tuple[PythonWorkspaceSymbol, ...]:
        return self.list_file_symbols(repository_rel_path)

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
