from __future__ import annotations

from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import QualityFileResultView
from suitcode.mcp.presenters import QualityPresenter
from suitcode.mcp.state import WorkspaceRegistry


class QualityMcpService:
    def __init__(self, registry: WorkspaceRegistry, quality_presenter: QualityPresenter) -> None:
        self._registry = registry
        self._quality_presenter = quality_presenter

    def list_quality_providers(self, workspace_id: str, repository_id: str) -> tuple[str, ...]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        return repository.quality.provider_ids

    def lint_file(self, workspace_id: str, repository_id: str, repository_rel_path: str, provider_id: str, is_fix: bool) -> QualityFileResultView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            result = repository.quality.lint_file(repository_rel_path, is_fix=is_fix, provider_id=provider_id)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._quality_presenter.quality_file_result_view(workspace_id, repository_id, provider_id, result)

    def format_file(self, workspace_id: str, repository_id: str, repository_rel_path: str, provider_id: str) -> QualityFileResultView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            result = repository.quality.format_file(repository_rel_path, provider_id=provider_id)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._quality_presenter.quality_file_result_view(workspace_id, repository_id, provider_id, result)
