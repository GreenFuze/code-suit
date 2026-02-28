from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import url2pathname

from suitcode.core.repository import Repository
from suitcode.providers.npm.symbol_models import NpmSymbolQuery, NpmWorkspaceSymbol
from suitcode.providers.shared.lsp import LspClient, LspWorkspaceSymbol, TypeScriptLanguageServerResolver
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader


class NpmSymbolService:
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

    def __init__(
        self,
        repository: Repository,
        workspace_loader: PackageJsonWorkspaceLoader | None = None,
        resolver: TypeScriptLanguageServerResolver | None = None,
        client_factory: Callable[[tuple[str, ...], Path], LspClient] | None = None,
    ) -> None:
        self._repository = repository
        self._workspace_loader = workspace_loader or PackageJsonWorkspaceLoader()
        self._resolver = resolver or TypeScriptLanguageServerResolver()
        self._client_factory = client_factory or (lambda command, cwd: LspClient(command, cwd))

    def get_symbols(self, query: str) -> tuple[NpmWorkspaceSymbol, ...]:
        symbol_query = self._validate_query(query)
        self._workspace_loader.load(self._repository.root)
        command = self._resolver.resolve(self._repository.root)
        with self._client_factory(command, self._repository.root) as client:
            client.initialize(self._repository.root)
            results = client.workspace_symbol(symbol_query.query)
        translated = tuple(
            item
            for item in (self._translate_symbol(result) for result in results)
            if item is not None
        )
        return tuple(
            sorted(
                translated,
                key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0),
            )
        )

    def _validate_query(self, query: str) -> NpmSymbolQuery:
        normalized = query.strip()
        if not normalized:
            raise ValueError("symbol query must not be empty")
        return NpmSymbolQuery(query=normalized)

    def _translate_symbol(self, symbol: LspWorkspaceSymbol) -> NpmWorkspaceSymbol | None:
        if symbol.location is None:
            return None
        file_path = self._path_from_uri(symbol.location.uri)
        if file_path is None or file_path.suffix.lower() not in self._JS_TS_EXTENSIONS:
            return None
        symbol_range = symbol.location.range
        return NpmWorkspaceSymbol(
            name=symbol.name,
            kind=self._SYMBOL_KIND_BY_CODE.get(symbol.kind, "unknown"),
            repository_rel_path=file_path.relative_to(self._repository.root).as_posix(),
            line_start=symbol_range.start.line + 1,
            line_end=symbol_range.end.line + 1,
            column_start=symbol_range.start.character + 1,
            column_end=symbol_range.end.character + 1,
            container_name=symbol.container_name,
            signature=symbol.container_name,
        )

    def _path_from_uri(self, uri: str) -> Path | None:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        resolved = Path(url2pathname(parsed.path)).resolve()
        try:
            resolved.relative_to(self._repository.root)
        except ValueError:
            return None
        return resolved
