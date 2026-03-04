from __future__ import annotations

from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.mcp.errors import McpNotFoundError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.models import (
    AddRepositoryResult,
    ListResult,
    OpenWorkspaceResult,
    ProviderDescriptorView,
    RepositorySupportView,
    RepositoryView,
    WorkspaceView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import ProviderPresenter, RepositoryPresenter, WorkspacePresenter
from suitcode.mcp.state import WorkspaceRegistry


class WorkspaceMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        provider_presenter: ProviderPresenter,
        workspace_presenter: WorkspacePresenter,
        repository_presenter: RepositoryPresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._provider_presenter = provider_presenter
        self._workspace_presenter = workspace_presenter
        self._repository_presenter = repository_presenter

    def list_supported_providers(self, limit: int | None = None, offset: int = 0) -> ListResult[ProviderDescriptorView]:
        items = tuple(self._provider_presenter.descriptor_view(descriptor) for descriptor in Workspace.supported_providers())
        return self._pagination.paginate(items, limit, offset)

    def inspect_repository_support(self, repository_path: str) -> RepositorySupportView:
        try:
            support = Repository.support_for_path(Path(repository_path))
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._provider_presenter.support_view(support)

    def open_workspace(self, repository_path: str) -> OpenWorkspaceResult:
        try:
            state = self._registry.open_workspace(repository_path)
        except ValueError as exc:
            if "No registered providers matched" in str(exc):
                raise McpUnsupportedRepositoryError(str(exc)) from exc
            raise McpValidationError(str(exc)) from exc
        return self._workspace_presenter.open_workspace_result(state.workspace, state.repository, state.reused)

    def list_workspaces(self, limit: int | None = None, offset: int = 0) -> ListResult[WorkspaceView]:
        items = tuple(self._workspace_presenter.workspace_view(workspace) for workspace in self._registry.list_workspaces())
        return self._pagination.paginate(items, limit, offset)

    def get_workspace(self, workspace_id: str) -> WorkspaceView:
        return self._workspace_presenter.workspace_view(self._registry.get_workspace(workspace_id))

    def close_workspace(self, workspace_id: str) -> None:
        self._registry.close_workspace(workspace_id)

    def list_workspace_repositories(self, workspace_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RepositoryView]:
        workspace = self._registry.get_workspace(workspace_id)
        items = tuple(self._repository_presenter.repository_view(repository) for repository in workspace.repositories)
        return self._pagination.paginate(items, limit, offset)

    def get_repository(self, workspace_id: str, repository_id: str) -> RepositoryView:
        return self._repository_presenter.repository_view(self._registry.get_repository(workspace_id, repository_id))

    def get_repository_by_path(self, workspace_id: str, repository_path: str) -> RepositoryView:
        workspace = self._registry.get_workspace(workspace_id)
        repository_root = Repository.root_candidate(Path(repository_path))
        if repository_root not in workspace.repository_roots:
            raise McpNotFoundError(f"repository `{repository_root}` is not tracked in workspace `{workspace_id}`")
        return self._repository_presenter.repository_view(workspace.get_repository(repository_root))

    def add_repository(self, workspace_id: str, repository_path: str) -> AddRepositoryResult:
        try:
            state = self._registry.add_repository(workspace_id, repository_path)
        except McpNotFoundError:
            raise
        except ValueError as exc:
            if "unsupported repository" in str(exc):
                raise McpUnsupportedRepositoryError(str(exc)) from exc
            raise McpValidationError(str(exc)) from exc
        return self._workspace_presenter.add_repository_result(
            workspace_id=workspace_id,
            owning_workspace_id=state.owning_workspace_id,
            repository=state.repository,
            reused=state.reused,
        )
