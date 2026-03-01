from __future__ import annotations

import hashlib
from pathlib import Path

from suitcode.core.models import normalize_repository_relative_path
from suitcode.core.repository import Repository
from suitcode.providers.npm.entity_delta import NpmEntityDeltaBuilder
from suitcode.providers.npm.eslint_runner import EslintRunner
from suitcode.providers.npm.prettier_runner import PrettierRunner
from suitcode.providers.npm.quality_models import (
    NpmFormatRunResult,
    NpmLintRunResult,
    NpmQualityOperationResult,
)
from suitcode.providers.npm.symbol_service import NpmFileSymbolService
from suitcode.providers.npm.tool_resolution import NpmQualityToolResolver


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
        self._repository = repository
        self._tool_resolver = tool_resolver or NpmQualityToolResolver(repository)
        self._eslint_runner = eslint_runner or EslintRunner(repository)
        self._prettier_runner = prettier_runner or PrettierRunner(repository)
        self._file_symbol_service = file_symbol_service or NpmFileSymbolService(repository)
        self._entity_delta_builder = entity_delta_builder or NpmEntityDeltaBuilder()

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
        file_path, normalized = self._resolve_repository_file(repository_rel_path)
        tool = self._tool_resolver.resolve_linter(file_path)
        content_sha_before = self._file_sha(file_path)
        entities_before = self._file_symbol_service.get_file_entities(normalized)
        run_result = self._eslint_runner.run(tool, file_path, is_fix)
        content_sha_after = self._file_sha(file_path)
        entities_after = self._file_symbol_service.get_file_entities(normalized)
        return NpmQualityOperationResult(
            repository_rel_path=normalized,
            tool=tool.tool,
            operation="lint",
            changed=content_sha_before != content_sha_after,
            success=True,
            message=run_result.message,
            diagnostics=run_result.diagnostics,
            entity_delta=self._entity_delta_builder.build(entities_before, entities_after),
            applied_fixes=is_fix and content_sha_before != content_sha_after,
            content_sha_before=content_sha_before,
            content_sha_after=content_sha_after,
        )

    def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
        file_path, normalized = self._resolve_repository_file(repository_rel_path)
        tool = self._tool_resolver.resolve_formatter(file_path)
        content_sha_before = self._file_sha(file_path)
        entities_before = self._file_symbol_service.get_file_entities(normalized)
        run_result = self._prettier_runner.run(tool, file_path)
        content_sha_after = self._file_sha(file_path)
        entities_after = self._file_symbol_service.get_file_entities(normalized)
        return NpmQualityOperationResult(
            repository_rel_path=normalized,
            tool=tool.tool,
            operation="format",
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
            raise ValueError(f"path escapes repository root: `{repository_rel_path}`") from exc
        if not file_path.exists():
            raise ValueError(f"file does not exist: `{repository_rel_path}`")
        if not file_path.is_file():
            raise ValueError(f"path is not a file: `{repository_rel_path}`")
        return file_path, normalized

    def _file_sha(self, file_path: Path) -> str:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
