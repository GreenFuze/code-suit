from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.providers.npm.entity_delta import NpmEntityDeltaBuilder
from suitcode.providers.npm.eslint_runner import EslintRunner
from suitcode.providers.npm.prettier_runner import PrettierRunner
from suitcode.providers.npm.quality_models import (
    NpmQualityOperationResult,
)
from suitcode.providers.npm.symbol_service import NpmFileSymbolService
from suitcode.providers.npm.tool_resolution import NpmQualityToolResolver
from suitcode.providers.shared.quality_file_pipeline import QualityFilePipeline

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class NpmQualityService:
    def __init__(
        self,
        repository: Repository,
        tool_resolver: NpmQualityToolResolver | None = None,
        eslint_runner: EslintRunner | None = None,
        prettier_runner: PrettierRunner | None = None,
        file_symbol_service: NpmFileSymbolService | None = None,
        entity_delta_builder: NpmEntityDeltaBuilder | None = None,
    ) -> None:
        self._tool_resolver = tool_resolver or NpmQualityToolResolver(repository)
        self._eslint_runner = eslint_runner or EslintRunner(repository)
        self._prettier_runner = prettier_runner or PrettierRunner(repository)
        self._file_symbol_service = file_symbol_service or NpmFileSymbolService(repository)
        self._entity_delta_builder = entity_delta_builder or NpmEntityDeltaBuilder()
        self._pipeline = QualityFilePipeline(
            repository.root,
            entity_reader=self._file_symbol_service.get_file_entities,
        )

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
        resolved = self._pipeline.resolve_file(repository_rel_path)
        tool = self._tool_resolver.resolve_linter(resolved.path)
        before = self._pipeline.capture_snapshot(resolved)
        run_result = self._eslint_runner.run(tool, resolved.path, is_fix)
        after = self._pipeline.capture_snapshot(resolved)
        return NpmQualityOperationResult(
            repository_rel_path=resolved.repository_rel_path,
            tool=tool.tool,
            operation="lint",
            changed=before.content_sha != after.content_sha,
            success=True,
            message=run_result.message,
            diagnostics=run_result.diagnostics,
            entity_delta=self._entity_delta_builder.build(before.entities, after.entities),
            applied_fixes=is_fix and before.content_sha != after.content_sha,
            content_sha_before=before.content_sha,
            content_sha_after=after.content_sha,
        )

    def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
        resolved = self._pipeline.resolve_file(repository_rel_path)
        tool = self._tool_resolver.resolve_formatter(resolved.path)
        before = self._pipeline.capture_snapshot(resolved)
        run_result = self._prettier_runner.run(tool, resolved.path)
        after = self._pipeline.capture_snapshot(resolved)
        return NpmQualityOperationResult(
            repository_rel_path=resolved.repository_rel_path,
            tool=tool.tool,
            operation="format",
            changed=before.content_sha != after.content_sha,
            success=True,
            message=run_result.message,
            diagnostics=tuple(),
            entity_delta=self._entity_delta_builder.build(before.entities, after.entities),
            applied_fixes=before.content_sha != after.content_sha,
            content_sha_before=before.content_sha,
            content_sha_after=after.content_sha,
        )
