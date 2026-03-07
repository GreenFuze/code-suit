from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.providers.python.entity_delta import PythonEntityDeltaBuilder
from suitcode.providers.python.quality_models import PythonQualityOperationResult
from suitcode.providers.python.ruff_runner import RuffRunner
from suitcode.providers.python.symbol_service import PythonFileSymbolService
from suitcode.providers.python.tool_resolution import PythonQualityToolResolver
from suitcode.providers.shared.quality_file_pipeline import QualityFilePipeline

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
        self._tool_resolver = tool_resolver or PythonQualityToolResolver(repository)
        self._ruff_runner = ruff_runner or RuffRunner()
        self._file_symbol_service = file_symbol_service or PythonFileSymbolService(repository)
        self._entity_delta_builder = entity_delta_builder or PythonEntityDeltaBuilder()
        self._pipeline = QualityFilePipeline(
            repository.root,
            entity_reader=self._file_symbol_service.get_file_symbols,
        )

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> PythonQualityOperationResult:
        resolved = self._pipeline.resolve_file(repository_rel_path)
        tool = self._tool_resolver.resolve(resolved.path)
        before = self._pipeline.capture_snapshot(resolved)
        run_result = self._ruff_runner.run_check(tool, resolved.path, is_fix)
        after = self._pipeline.capture_snapshot(resolved)
        return PythonQualityOperationResult(
            repository_rel_path=resolved.repository_rel_path,
            tool=tool.tool,
            operation='lint',
            changed=before.content_sha != after.content_sha,
            success=True,
            message=run_result.message,
            diagnostics=run_result.diagnostics,
            entity_delta=self._entity_delta_builder.build(before.entities, after.entities),
            applied_fixes=is_fix and before.content_sha != after.content_sha,
            content_sha_before=before.content_sha,
            content_sha_after=after.content_sha,
        )

    def format_file(self, repository_rel_path: str) -> PythonQualityOperationResult:
        resolved = self._pipeline.resolve_file(repository_rel_path)
        tool = self._tool_resolver.resolve(resolved.path)
        before = self._pipeline.capture_snapshot(resolved)
        run_result = self._ruff_runner.run_format(tool, resolved.path)
        after = self._pipeline.capture_snapshot(resolved)
        return PythonQualityOperationResult(
            repository_rel_path=resolved.repository_rel_path,
            tool=tool.tool,
            operation='format',
            changed=before.content_sha != after.content_sha,
            success=True,
            message=run_result.message,
            diagnostics=tuple(),
            entity_delta=self._entity_delta_builder.build(before.entities, after.entities),
            applied_fixes=before.content_sha != after.content_sha,
            content_sha_before=before.content_sha,
            content_sha_after=after.content_sha,
        )
