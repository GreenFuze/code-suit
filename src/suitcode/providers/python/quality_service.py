from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.models import normalize_repository_relative_path
from suitcode.providers.python.entity_delta import PythonEntityDeltaBuilder
from suitcode.providers.python.quality_models import PythonQualityOperationResult
from suitcode.providers.python.ruff_runner import RuffRunner
from suitcode.providers.python.symbol_service import PythonFileSymbolService
from suitcode.providers.python.tool_resolution import PythonQualityToolResolver

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class PythonQualityService:
    def __init__(
        self,
        repository: Repository,
        tool_resolver: PythonQualityToolResolver | None = None,
        ruff_runner: RuffRunner | None = None,
        file_symbol_service: PythonFileSymbolService | None = None,
        entity_delta_builder: PythonEntityDeltaBuilder | None = None,
    ) -> None:
        self._repository = repository
        self._tool_resolver = tool_resolver or PythonQualityToolResolver(repository)
        self._ruff_runner = ruff_runner or RuffRunner()
        self._file_symbol_service = file_symbol_service or PythonFileSymbolService(repository)
        self._entity_delta_builder = entity_delta_builder or PythonEntityDeltaBuilder()

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> PythonQualityOperationResult:
        file_path, normalized = self._resolve_repository_file(repository_rel_path)
        tool = self._tool_resolver.resolve(file_path)
        content_sha_before = self._file_sha(file_path)
        entities_before = self._file_symbol_service.get_file_symbols(normalized)
        run_result = self._ruff_runner.run_check(tool, file_path, is_fix)
        content_sha_after = self._file_sha(file_path)
        entities_after = self._file_symbol_service.get_file_symbols(normalized)
        return PythonQualityOperationResult(
            repository_rel_path=normalized,
            tool=tool.tool,
            operation='lint',
            changed=content_sha_before != content_sha_after,
            success=True,
            message=run_result.message,
            diagnostics=run_result.diagnostics,
            entity_delta=self._entity_delta_builder.build(entities_before, entities_after),
            applied_fixes=is_fix and content_sha_before != content_sha_after,
            content_sha_before=content_sha_before,
            content_sha_after=content_sha_after,
        )

    def format_file(self, repository_rel_path: str) -> PythonQualityOperationResult:
        file_path, normalized = self._resolve_repository_file(repository_rel_path)
        tool = self._tool_resolver.resolve(file_path)
        content_sha_before = self._file_sha(file_path)
        entities_before = self._file_symbol_service.get_file_symbols(normalized)
        run_result = self._ruff_runner.run_format(tool, file_path)
        content_sha_after = self._file_sha(file_path)
        entities_after = self._file_symbol_service.get_file_symbols(normalized)
        return PythonQualityOperationResult(
            repository_rel_path=normalized,
            tool=tool.tool,
            operation='format',
            changed=content_sha_before != content_sha_after,
            success=True,
            message=run_result.message,
            diagnostics=tuple(),
            entity_delta=self._entity_delta_builder.build(entities_before, entities_after),
            applied_fixes=content_sha_before != content_sha_after,
            content_sha_before=content_sha_before,
            content_sha_after=content_sha_after,
        )

    def _resolve_repository_file(self, repository_rel_path: str) -> tuple[Path, str]:
        normalized = normalize_repository_relative_path(repository_rel_path)
        file_path = (self._repository.root / normalized).resolve()
        try:
            file_path.relative_to(self._repository.root)
        except ValueError as exc:
            raise ValueError(f'path escapes repository root: `{repository_rel_path}`') from exc
        if not file_path.exists():
            raise ValueError(f'file does not exist: `{repository_rel_path}`')
        if not file_path.is_file():
            raise ValueError(f'path is not a file: `{repository_rel_path}`')
        return file_path, normalized

    def _file_sha(self, file_path: Path) -> str:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
