from __future__ import annotations

from suitcode.mcp.errors import McpNotFoundError
from suitcode.mcp.models import (
    AggregatorView,
    ComponentDependencyEdgeView,
    ComponentView,
    DependencyRefView,
    ExternalPackageView,
    FileView,
    ListResult,
    PackageManagerView,
    RunnerView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import ArchitecturePresenter, IntelligencePresenter
from suitcode.mcp.state import WorkspaceRegistry


class ArchitectureMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        architecture_presenter: ArchitecturePresenter,
        intelligence_presenter: IntelligencePresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._architecture_presenter = architecture_presenter
        self._intelligence_presenter = intelligence_presenter

    def list_components(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ComponentView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.component_view(item) for item in repository.arch.get_components())
        return self._pagination.paginate(items, limit, offset)

    def list_aggregators(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[AggregatorView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.aggregator_view(item) for item in repository.arch.get_aggregators())
        return self._pagination.paginate(items, limit, offset)

    def list_runners(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RunnerView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.runner_view(item) for item in repository.arch.get_runners())
        return self._pagination.paginate(items, limit, offset)

    def list_package_managers(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[PackageManagerView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.package_manager_view(item) for item in repository.arch.get_package_managers())
        return self._pagination.paginate(items, limit, offset)

    def list_external_packages(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ExternalPackageView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.external_package_view(item) for item in repository.arch.get_external_packages())
        return self._pagination.paginate(items, limit, offset)

    def list_files(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[FileView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._architecture_presenter.file_view(item) for item in repository.arch.get_files())
        return self._pagination.paginate(items, limit, offset)

    def get_component_dependencies(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[DependencyRefView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            dependencies = repository.arch.get_component_dependencies(component_id)
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        items = tuple(self._intelligence_presenter.dependency_ref_view(item) for item in dependencies)
        return self._pagination.paginate(items, limit, offset)

    def list_component_dependency_edges(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ComponentDependencyEdgeView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            edges = repository.arch.get_component_dependency_edges(component_id)
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        items = tuple(self._intelligence_presenter.component_dependency_edge_view(item) for item in edges)
        return self._pagination.paginate(items, limit, offset)

    def get_component_dependents(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[str]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            dependents = repository.arch.get_component_dependents(component_id)
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return self._pagination.paginate(dependents, limit, offset)
