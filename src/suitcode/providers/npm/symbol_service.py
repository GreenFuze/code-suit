from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from fnmatch import fnmatchcase
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.models.ids import normalize_repository_relative_path
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
        attachment_root: Path | None = None,
        attachment_root_rel_path: str = "",
        source_roots: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._workspace_loader = workspace_loader or PackageJsonWorkspaceLoader()
        self._attachment_root = (attachment_root or repository.root).expanduser().resolve()
        self._attachment_root_rel_path = attachment_root_rel_path.strip().strip("/").replace("\\", "/")
        self._source_roots = source_roots
        self._resolver = resolver or TypeScriptLanguageServerResolver()
        super().__init__(
            repository=repository,
            ensure_ready=self._ensure_workspace,
            resolver=self._resolver,
            supported_extensions=self._JS_TS_EXTENSIONS,
            symbol_kind_by_code=self._SYMBOL_KIND_BY_CODE,
            ignored_directories=self._IGNORED_DIRECTORIES,
            symbol_factory=self._to_npm_symbol,
            client_factory=client_factory,
            session_manager=session_manager,
            attachment_root=self._attachment_root,
            attachment_root_rel_path=attachment_root_rel_path,
            included_repository_rel_roots=source_roots,
            enable_workspace_symbol_fallback=False,
        )

    def _ensure_workspace(self) -> None:
        self._workspace_loader.load(self._attachment_root)

    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("symbol query must not be empty")
        matches: list[NpmWorkspaceSymbol] = []
        for repository_rel_path in self._iter_source_files():
            if not self._could_contain_symbol_query(repository_rel_path, normalized_query, is_case_sensitive):
                continue
            for symbol in self._typescript_ast_file_symbols(repository_rel_path):
                if self._matches_query(symbol.name, normalized_query, is_case_sensitive):
                    matches.append(symbol)
        return tuple(
            sorted(
                matches,
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
    ) -> tuple[NpmWorkspaceSymbol, ...]:
        symbols = super().list_file_symbols(
            repository_rel_path,
            query=query,
            is_case_sensitive=is_case_sensitive,
        )
        if symbols:
            return symbols
        try:
            symbols = self._typescript_ast_file_symbols(repository_rel_path)
        except (AttributeError, ValueError):
            symbols = tuple()
        if query is not None:
            normalized_query = query.strip()
            if not normalized_query:
                raise ValueError("symbol query must not be empty")
            symbols = tuple(
                item for item in symbols if self._matches_query(item.name, normalized_query, is_case_sensitive)
            )
        return symbols

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        locations = list(
            super().find_references(
                repository_rel_path,
                line,
                column,
                include_definition=include_definition,
            )
        )
        try:
            ast_locations = self._typescript_ast_reference_locations(
                repository_rel_path,
                line,
                column,
                include_definition=include_definition,
            )
        except (AttributeError, ValueError):
            ast_locations = tuple()
        for item in ast_locations:
            if item not in locations:
                locations.append(item)
        return tuple(sorted(locations, key=lambda item: (item[0], item[1], item[3], item[2], item[4])))

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

    def _typescript_ast_file_symbols(self, repository_rel_path: str) -> tuple[NpmWorkspaceSymbol, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        absolute_path = (self._repository.root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self._attachment_root)
        except ValueError:
            return tuple()
        if absolute_path.suffix.lower() not in self._JS_TS_EXTENSIONS:
            return tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")
        node = self._resolver.resolve_node_path()
        typescript_library = self._resolver.resolve_typescript_library_path(self._attachment_root)
        script_path = resources.files("suitcode.providers.npm").joinpath("ts_symbols.cjs")
        command = (
            node,
            str(script_path),
            str(self._repository.root),
            str(absolute_path),
            typescript_library,
        )
        try:
            result = subprocess.run(
                command,
                cwd=self._attachment_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or "unknown TypeScript symbol-analysis error"
            raise ValueError(f"unable to resolve deterministic TypeScript symbols: {message}") from exc
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("TypeScript symbol analysis returned invalid JSON") from exc
        return self._coerce_typescript_symbols(payload)

    def _typescript_ast_reference_locations(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        *,
        include_definition: bool,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        if line < 1 or column < 1:
            raise ValueError("line and column must be >= 1")
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        absolute_path = (self._repository.root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self._attachment_root)
        except ValueError:
            return tuple()
        if absolute_path.suffix.lower() not in self._JS_TS_EXTENSIONS:
            return tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")
        node = self._resolver.resolve_node_path()
        typescript_library = self._resolver.resolve_typescript_library_path(self._attachment_root)
        script_path = resources.files("suitcode.providers.npm").joinpath("ts_references.cjs")
        command = (
            node,
            str(script_path),
            str(self._repository.root),
            str(self._attachment_root),
            str(absolute_path),
            str(line),
            str(column),
            "true" if include_definition else "false",
            typescript_library,
        )
        try:
            result = subprocess.run(
                command,
                cwd=self._attachment_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or "unknown TypeScript reference-analysis error"
            raise ValueError(f"unable to resolve deterministic TypeScript references: {message}") from exc
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("TypeScript reference analysis returned invalid JSON") from exc
        return self._coerce_typescript_reference_locations(payload)

    def _iter_source_files(self) -> tuple[str, ...]:
        roots = self._source_roots
        if roots is None:
            roots = frozenset({self._attachment_root_rel_path or "."})
        files: list[str] = []
        for root in sorted(roots):
            normalized_root = root.strip().strip("/").replace("\\", "/")
            absolute_root = (self._repository.root / normalized_root).resolve() if normalized_root != "." else self._repository.root
            try:
                absolute_root.relative_to(self._attachment_root)
            except ValueError:
                continue
            if not absolute_root.exists():
                continue
            for file_path in absolute_root.rglob("*"):
                if not file_path.is_file() or file_path.suffix.lower() not in self._JS_TS_EXTENSIONS:
                    continue
                parts = file_path.relative_to(absolute_root).parts[:-1]
                if any(part in self._IGNORED_DIRECTORIES or part.startswith(".") for part in parts):
                    continue
                files.append(file_path.relative_to(self._repository.root).as_posix())
        return tuple(sorted(set(files)))

    def _could_contain_symbol_query(self, repository_rel_path: str, query: str, is_case_sensitive: bool) -> bool:
        if "*" in query or "?" in query:
            return True
        absolute_path = (self._repository.root / repository_rel_path).resolve()
        try:
            content = absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = absolute_path.read_text(encoding="utf-8", errors="ignore")
        candidate_content = content if is_case_sensitive else content.casefold()
        candidate_query = query if is_case_sensitive else query.casefold()
        return candidate_query in candidate_content

    @staticmethod
    def _coerce_typescript_symbols(payload: object) -> tuple[NpmWorkspaceSymbol, ...]:
        if not isinstance(payload, dict):
            raise ValueError("TypeScript symbol analysis returned an invalid payload shape")
        raw_symbols = payload.get("symbols")
        if not isinstance(raw_symbols, list):
            raise ValueError("TypeScript symbol analysis field `symbols` must be a list")
        items: list[NpmWorkspaceSymbol] = []
        seen: set[tuple[object, ...]] = set()
        for item in raw_symbols:
            if not isinstance(item, dict):
                raise ValueError("TypeScript symbol analysis items must be objects")
            name = item.get("name")
            kind = item.get("kind")
            path = item.get("path")
            line_start = item.get("line_start")
            line_end = item.get("line_end")
            column_start = item.get("column_start")
            column_end = item.get("column_end")
            container_name = item.get("container_name")
            signature = item.get("signature")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("TypeScript symbol analysis item `name` must be a non-empty string")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("TypeScript symbol analysis item `kind` must be a non-empty string")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("TypeScript symbol analysis item `path` must be a non-empty string")
            if not isinstance(line_start, int) or line_start < 1:
                raise ValueError("TypeScript symbol analysis item `line_start` must be a positive integer")
            if not isinstance(column_start, int) or column_start < 1:
                raise ValueError("TypeScript symbol analysis item `column_start` must be a positive integer")
            if not isinstance(line_end, int) or line_end < line_start:
                raise ValueError("TypeScript symbol analysis item `line_end` must be a valid integer")
            if not isinstance(column_end, int) or column_end < column_start:
                raise ValueError("TypeScript symbol analysis item `column_end` must be a valid integer")
            if container_name is not None and not isinstance(container_name, str):
                raise ValueError("TypeScript symbol analysis item `container_name` must be a string when present")
            if signature is not None and not isinstance(signature, str):
                raise ValueError("TypeScript symbol analysis item `signature` must be a string when present")
            key = (path, kind, name, line_start, line_end, column_start, column_end)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                NpmWorkspaceSymbol(
                    name=name.strip(),
                    kind=kind.strip(),
                    repository_rel_path=normalize_repository_relative_path(path),
                    line_start=line_start,
                    line_end=line_end,
                    column_start=column_start,
                    column_end=column_end,
                    container_name=container_name,
                    signature=signature,
                )
            )
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    item.name,
                    item.kind,
                    item.line_start or 0,
                    item.column_start or 0,
                ),
            )
        )

    @staticmethod
    def _coerce_typescript_reference_locations(payload: object) -> tuple[tuple[str, int, int, int, int], ...]:
        if not isinstance(payload, dict):
            raise ValueError("TypeScript reference analysis returned an invalid payload shape")
        raw_references = payload.get("references")
        if not isinstance(raw_references, list):
            raise ValueError("TypeScript reference analysis field `references` must be a list")
        locations: list[tuple[str, int, int, int, int]] = []
        seen: set[tuple[str, int, int, int, int]] = set()
        for item in raw_references:
            if not isinstance(item, dict):
                raise ValueError("TypeScript reference analysis items must be objects")
            path = item.get("path")
            line_start = item.get("line_start")
            line_end = item.get("line_end")
            column_start = item.get("column_start")
            column_end = item.get("column_end")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("TypeScript reference analysis item `path` must be a non-empty string")
            if not isinstance(line_start, int) or line_start < 1:
                raise ValueError("TypeScript reference analysis item `line_start` must be a positive integer")
            if not isinstance(line_end, int) or line_end < line_start:
                raise ValueError("TypeScript reference analysis item `line_end` must be a valid integer")
            if not isinstance(column_start, int) or column_start < 1:
                raise ValueError("TypeScript reference analysis item `column_start` must be a positive integer")
            if not isinstance(column_end, int) or column_end < 1:
                raise ValueError("TypeScript reference analysis item `column_end` must be a positive integer")
            if line_start == line_end and column_end < column_start:
                raise ValueError("TypeScript reference analysis item `column_end` must be >= `column_start` on one line")
            location = (
                normalize_repository_relative_path(path),
                line_start,
                line_end,
                column_start,
                column_end,
            )
            if location in seen:
                continue
            seen.add(location)
            locations.append(location)
        return tuple(sorted(locations, key=lambda item: (item[0], item[1], item[3], item[2], item[4])))

    @staticmethod
    def _matches_query(symbol_name: str, query: str, is_case_sensitive: bool) -> bool:
        candidate_name = symbol_name if is_case_sensitive else symbol_name.casefold()
        candidate_query = query if is_case_sensitive else query.casefold()
        if "*" in query or "?" in query:
            return fnmatchcase(candidate_name, candidate_query)
        return candidate_name == candidate_query


class NpmSymbolService(_NpmSymbolServiceBase):
    pass


class NpmFileSymbolService(_NpmSymbolServiceBase):
    def get_file_entities(self, repository_rel_path: str) -> tuple[NpmWorkspaceSymbol, ...]:
        return self.list_file_symbols(repository_rel_path)
