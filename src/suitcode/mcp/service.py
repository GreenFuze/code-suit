from __future__ import annotations

from suitcode.core.code.models import SymbolLookupTarget
from suitcode.core.tests.models import RelatedTestTarget
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.mcp.errors import McpNotFoundError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.models import (
    AggregatorView,
    ArchitectureSnapshotView,
    ComponentView,
    ExternalPackageView,
    FileView,
    FileOwnerView,
    ListResult,
    LocationView,
    OpenWorkspaceResult,
    PackageManagerView,
    ProviderDescriptorView,
    QualityFileResultView,
    QualitySnapshotView,
    RelatedTestView,
    RepositorySnapshotView,
    RepositorySummaryView,
    RepositorySupportView,
    RepositoryView,
    RunnerView,
    SymbolView,
    TestsSnapshotView,
    TestDefinitionView,
    WorkspaceView,
    AddRepositoryResult,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import (
    ArchitecturePresenter,
    CodePresenter,
    ProviderPresenter,
    QualityPresenter,
    RepositoryPresenter,
    RepositorySummaryPresenter,
    TestPresenter,
    WorkspacePresenter,
    OwnershipPresenter,
)
from suitcode.mcp.state import WorkspaceRegistry


class SuitMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry | None = None,
        pagination: PaginationPolicy | None = None,
    ) -> None:
        self._registry = registry or WorkspaceRegistry()
        self._pagination = pagination or PaginationPolicy()
        self._provider_presenter = ProviderPresenter()
        self._workspace_presenter = WorkspacePresenter()
        self._repository_presenter = RepositoryPresenter()
        self._architecture_presenter = ArchitecturePresenter()
        self._code_presenter = CodePresenter()
        self._test_presenter = TestPresenter()
        self._quality_presenter = QualityPresenter()
        self._ownership_presenter = OwnershipPresenter()
        self._repository_summary_presenter = RepositorySummaryPresenter()

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

    def find_symbols(
        self,
        workspace_id: str,
        repository_id: str,
        query: str,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            items = tuple(
                self._code_presenter.symbol_view(item)
                for item in repository.code.get_symbol(query, is_case_sensitive=is_case_sensitive)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def list_symbols_in_file(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        if query is not None and not query.strip():
            raise McpValidationError("query must not be blank")
        try:
            items = tuple(
                self._code_presenter.symbol_view(item)
                for item in repository.code.list_symbols_in_file(
                    repository_rel_path,
                    query=query,
                    is_case_sensitive=is_case_sensitive,
                )
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def get_file_owner(self, workspace_id: str, repository_id: str, repository_rel_path: str) -> FileOwnerView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            file_owner = repository.get_file_owner(repository_rel_path)
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return self._ownership_presenter.file_owner_view(file_owner)

    def list_files_by_owner(
        self,
        workspace_id: str,
        repository_id: str,
        owner_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[FileView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            items = tuple(
                self._architecture_presenter.file_view(item)
                for item in repository.list_files_by_owner(owner_id)
            )
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def find_definition(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = SymbolLookupTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                line=line,
                column=column,
            )
            items = tuple(
                self._code_presenter.location_view(item)
                for item in repository.code.find_definition(target)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def find_references(
        self,
        workspace_id: str,
        repository_id: str,
        include_definition: bool = False,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = SymbolLookupTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                line=line,
                column=column,
            )
            items = tuple(
                self._code_presenter.location_view(item)
                for item in repository.code.find_references(target, include_definition=include_definition)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

    def list_tests(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[TestDefinitionView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._test_presenter.test_view(item) for item in repository.tests.get_tests())
        return self._pagination.paginate(items, limit, offset)

    def get_related_tests(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[RelatedTestView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = RelatedTestTarget(repository_rel_path=repository_rel_path, owner_id=owner_id)
            items = tuple(
                self._test_presenter.related_test_view(item)
                for item in repository.tests.get_related_tests(target)
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)

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

    def workspace_snapshot(self, workspace_id: str):
        return self._workspace_presenter.workspace_snapshot(self._registry.get_workspace(workspace_id))

    def repository_snapshot(self, workspace_id: str, repository_id: str):
        return self._repository_presenter.repository_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def architecture_snapshot(self, workspace_id: str, repository_id: str):
        return self._architecture_presenter.architecture_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def tests_snapshot(self, workspace_id: str, repository_id: str):
        return self._test_presenter.tests_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def quality_snapshot(self, workspace_id: str, repository_id: str):
        return self._quality_presenter.quality_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def repository_summary(
        self,
        workspace_id: str,
        repository_id: str,
        preview_limit: int = 10,
    ) -> RepositorySummaryView:
        if preview_limit < 1 or preview_limit > 25:
            raise McpValidationError("preview_limit must be between 1 and 25")
        repository = self._registry.get_repository(workspace_id, repository_id)
        return self._repository_summary_presenter.summary_view(repository, preview_limit)
