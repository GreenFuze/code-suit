from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol
from suitcode.providers.shared.structural_symbols import filter_structural_symbols


@dataclass(frozen=True)
class PythonStructuralSymbolService:
    repository_root: Path
    attachment_root: Path

    def list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        absolute_path = (self.repository_root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self.attachment_root)
        except ValueError:
            return tuple()
        if absolute_path.suffix.lower() != ".py":
            return tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")
        source = absolute_path.read_text(encoding="utf-8")
        try:
            module = ast.parse(source, filename=str(absolute_path))
        except SyntaxError as exc:
            raise ValueError(f"unable to parse deterministic Python symbols: {exc}") from exc
        symbols = self._module_symbols(normalized_path, module)
        return filter_structural_symbols(symbols, query=query, is_case_sensitive=is_case_sensitive)

    def _module_symbols(self, repository_rel_path: str, module: ast.Module) -> tuple[PythonWorkspaceSymbol, ...]:
        items: list[PythonWorkspaceSymbol] = []
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                items.append(self._symbol(repository_rel_path, node.name, "function", node))
                continue
            if isinstance(node, ast.ClassDef):
                items.append(self._symbol(repository_rel_path, node.name, "class", node))
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        items.append(self._symbol(repository_rel_path, f"{node.name}.{child.name}", "method", child))
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                for name in self._assignment_names(node):
                    items.append(self._symbol(repository_rel_path, name, "variable", node))
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.kind, item.line_start or 0, item.column_start or 0),
            )
        )

    @staticmethod
    def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        names: list[str] = []
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        return tuple(names)

    @staticmethod
    def _symbol(repository_rel_path: str, name: str, kind: str, node: ast.AST) -> PythonWorkspaceSymbol:
        line_start = getattr(node, "lineno", None)
        column_start = getattr(node, "col_offset", None)
        line_end = getattr(node, "end_lineno", None) or line_start
        column_end = getattr(node, "end_col_offset", None)
        return PythonWorkspaceSymbol(
            name=name,
            kind=kind,
            repository_rel_path=repository_rel_path,
            line_start=line_start,
            line_end=line_end,
            column_start=(column_start + 1 if isinstance(column_start, int) else None),
            column_end=(column_end + 1 if isinstance(column_end, int) else None),
            container_name=None,
            signature=None,
        )
