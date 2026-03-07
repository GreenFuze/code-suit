from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient, TypeScriptLanguageServerResolver
from suitcode.providers.shared.lsp_code import LspRepositorySymbol, LspSessionManager, LspSymbolServiceBase
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class _NpmSymbolServiceBase(LspSymbolServiceBase[NpmWorkspaceSymbol]):
    _JS_TS_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})
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
        15: "string",
        16: "number",
        17: "boolean",
        18: "array",
        19: "object",
        20: "key",
        21: "null",
        22: "enum-member",
        23: "struct",
        24: "event",
        25: "operator",
        26: "type-parameter",
    }
    _IGNORED_DIRECTORIES = frozenset({"__pycache__", ".git", ".venv", "venv", "env", "node_modules"})

    def __init__(
        self,
        repository: Repository,
        workspace_loader: PackageJsonWorkspaceLoader | None = None,
        resolver: TypeScriptLanguageServerResolver | None = None,
        client_factory: Callable[..., LspClient] | None = None,
        session_manager: LspSessionManager | None = None,
    ) -> None:
        self._repository = repository
        self._workspace_loader = workspace_loader or PackageJsonWorkspaceLoader()
        super().__init__(
            repository=repository,
            ensure_ready=self._ensure_workspace,
            resolver=resolver or TypeScriptLanguageServerResolver(),
            supported_extensions=self._JS_TS_EXTENSIONS,
            symbol_kind_by_code=self._SYMBOL_KIND_BY_CODE,
            ignored_directories=self._IGNORED_DIRECTORIES,
            symbol_factory=self._to_npm_symbol,
            client_factory=client_factory,
            session_manager=session_manager,
        )

    def _ensure_workspace(self) -> None:
        self._workspace_loader.load(self._repository.root)

    @staticmethod
    def _to_npm_symbol(symbol: LspRepositorySymbol) -> NpmWorkspaceSymbol:
        return NpmWorkspaceSymbol(
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


class NpmSymbolService(_NpmSymbolServiceBase):
    pass


class NpmFileSymbolService(_NpmSymbolServiceBase):
    def get_file_entities(self, repository_rel_path: str) -> tuple[NpmWorkspaceSymbol, ...]:
        return self.list_file_symbols(repository_rel_path)
