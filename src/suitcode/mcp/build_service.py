from __future__ import annotations

from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import (
    BuildExecutionResultView,
    BuildProjectResultView,
    BuildTargetDescriptionView,
    ListResult,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import BuildPresenter
from suitcode.mcp.state import WorkspaceRegistry


class BuildMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        build_presenter: BuildPresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._build_presenter = build_presenter

    def list_build_targets(
        self,
        workspace_id: str,
        repository_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[BuildTargetDescriptionView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(
            self._build_presenter.build_target_description_view(item)
            for item in repository.list_build_targets()
        )
        return self._pagination.paginate(items, limit=limit, offset=offset)

    def describe_build_target(
        self,
        workspace_id: str,
        repository_id: str,
        action_id: str,
    ) -> BuildTargetDescriptionView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = repository.describe_build_target(action_id)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._build_presenter.build_target_description_view(target)

    def build_target(
        self,
        workspace_id: str,
        repository_id: str,
        action_id: str,
        timeout_seconds: int = 300,
    ) -> BuildExecutionResultView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            result = repository.build_target(action_id, timeout_seconds=timeout_seconds)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._build_presenter.build_execution_result_view(result)

    def build_project(
        self,
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int = 300,
    ) -> BuildProjectResultView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            result = repository.build_project(timeout_seconds=timeout_seconds)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._build_presenter.build_project_result_view(result)
