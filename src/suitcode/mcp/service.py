from __future__ import annotations

from suitcode.mcp.action_service import ActionMcpService
from suitcode.mcp.architecture_service import ArchitectureMcpService
from suitcode.mcp.build_service import BuildMcpService
from suitcode.mcp.code_service import CodeMcpService
from suitcode.mcp.context_service import ContextMcpService
from suitcode.mcp.errors import McpNotFoundError
from suitcode.mcp.models import (
    AddRepositoryResult,
    AggregatorView,
    ActionView,
    ArchitectureSnapshotView,
    BuildExecutionResultView,
    BuildProjectResultView,
    BuildTargetDescriptionView,
    ChangeImpactView,
    ComponentDependencyEdgeView,
    ComponentContextView,
    ComponentView,
    DependencyRefView,
    ExternalPackageView,
    FileContextView,
    FileOwnerView,
    FileView,
    ImpactSummaryView,
    ListResult,
    LocationView,
    OpenWorkspaceResult,
    PackageManagerView,
    ProviderDescriptorView,
    QualityFileResultView,
    QualitySnapshotView,
    RelatedTestView,
    RunTestTargetsView,
    RepositorySnapshotView,
    RepositorySummaryView,
    RepositorySupportView,
    RepositoryView,
    RunnerContextView,
    RunnerExecutionResultView,
    RunnerView,
    SymbolContextView,
    SymbolView,
    TestsSnapshotView,
    TestDefinitionView,
    TestTargetDescriptionView,
    WorkspaceView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import (
    ArchitecturePresenter,
    ActionPresenter,
    BuildPresenter,
    ChangeImpactPresenter,
    CodePresenter,
    IntelligencePresenter,
    OwnershipPresenter,
    ProviderPresenter,
    QualityPresenter,
    RepositoryPresenter,
    RepositorySummaryPresenter,
    RunnerPresenter,
    TestPresenter,
    WorkspacePresenter,
)
from suitcode.mcp.quality_service import QualityMcpService
from suitcode.mcp.runner_service import RunnerMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.mcp.test_service import TestMcpService
from suitcode.mcp.workspace_service import WorkspaceMcpService


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
        self._action_presenter = ActionPresenter()
        self._build_presenter = BuildPresenter()
        self._code_presenter = CodePresenter()
        self._test_presenter = TestPresenter()
        self._runner_presenter = RunnerPresenter()
        self._quality_presenter = QualityPresenter()
        self._ownership_presenter = OwnershipPresenter()
        self._repository_summary_presenter = RepositorySummaryPresenter()
        self._intelligence_presenter = IntelligencePresenter()
        self._change_impact_presenter = ChangeImpactPresenter()

        self._workspace_service = WorkspaceMcpService(
            self._registry,
            self._pagination,
            self._provider_presenter,
            self._workspace_presenter,
            self._repository_presenter,
        )
        self._architecture_service = ArchitectureMcpService(
            self._registry,
            self._pagination,
            self._architecture_presenter,
            self._intelligence_presenter,
        )
        self._action_service = ActionMcpService(
            self._registry,
            self._pagination,
            self._action_presenter,
        )
        self._code_service = CodeMcpService(
            self._registry,
            self._pagination,
            self._code_presenter,
        )
        self._build_service = BuildMcpService(
            self._registry,
            self._pagination,
            self._build_presenter,
        )
        self._test_service = TestMcpService(
            self._registry,
            self._pagination,
            self._test_presenter,
        )
        self._quality_service = QualityMcpService(
            self._registry,
            self._quality_presenter,
        )
        self._runner_service = RunnerMcpService(
            self._registry,
            self._runner_presenter,
        )
        self._context_service = ContextMcpService(
            self._registry,
            self._intelligence_presenter,
            self._repository_summary_presenter,
            self._change_impact_presenter,
        )

    def list_supported_providers(self, limit: int | None = None, offset: int = 0) -> ListResult[ProviderDescriptorView]:
        return self._workspace_service.list_supported_providers(limit=limit, offset=offset)

    def inspect_repository_support(self, repository_path: str) -> RepositorySupportView:
        return self._workspace_service.inspect_repository_support(repository_path)

    def open_workspace(self, repository_path: str) -> OpenWorkspaceResult:
        return self._workspace_service.open_workspace(repository_path)

    def list_workspaces(self, limit: int | None = None, offset: int = 0) -> ListResult[WorkspaceView]:
        return self._workspace_service.list_workspaces(limit=limit, offset=offset)

    def get_workspace(self, workspace_id: str) -> WorkspaceView:
        return self._workspace_service.get_workspace(workspace_id)

    def close_workspace(self, workspace_id: str) -> None:
        self._workspace_service.close_workspace(workspace_id)

    def list_workspace_repositories(self, workspace_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RepositoryView]:
        return self._workspace_service.list_workspace_repositories(workspace_id, limit=limit, offset=offset)

    def get_repository(self, workspace_id: str, repository_id: str) -> RepositoryView:
        return self._workspace_service.get_repository(workspace_id, repository_id)

    def get_repository_by_path(self, workspace_id: str, repository_path: str) -> RepositoryView:
        return self._workspace_service.get_repository_by_path(workspace_id, repository_path)

    def add_repository(self, workspace_id: str, repository_path: str) -> AddRepositoryResult:
        return self._workspace_service.add_repository(workspace_id, repository_path)

    def list_components(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ComponentView]:
        return self._architecture_service.list_components(workspace_id, repository_id, limit=limit, offset=offset)

    def list_aggregators(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[AggregatorView]:
        return self._architecture_service.list_aggregators(workspace_id, repository_id, limit=limit, offset=offset)

    def list_runners(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RunnerView]:
        return self._architecture_service.list_runners(workspace_id, repository_id, limit=limit, offset=offset)

    def list_package_managers(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[PackageManagerView]:
        return self._architecture_service.list_package_managers(workspace_id, repository_id, limit=limit, offset=offset)

    def list_external_packages(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ExternalPackageView]:
        return self._architecture_service.list_external_packages(workspace_id, repository_id, limit=limit, offset=offset)

    def list_files(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[FileView]:
        return self._architecture_service.list_files(workspace_id, repository_id, limit=limit, offset=offset)

    def list_actions(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        component_id: str | None = None,
        runner_id: str | None = None,
        test_id: str | None = None,
        action_kinds: tuple[str, ...] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ActionView]:
        return self._action_service.list_actions(
            workspace_id,
            repository_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            component_id=component_id,
            runner_id=runner_id,
            test_id=test_id,
            action_kinds=action_kinds,
            limit=limit,
            offset=offset,
        )

    def list_build_targets(
        self,
        workspace_id: str,
        repository_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[BuildTargetDescriptionView]:
        return self._build_service.list_build_targets(
            workspace_id,
            repository_id,
            limit=limit,
            offset=offset,
        )

    def describe_build_target(
        self,
        workspace_id: str,
        repository_id: str,
        action_id: str,
    ) -> BuildTargetDescriptionView:
        return self._build_service.describe_build_target(
            workspace_id,
            repository_id,
            action_id=action_id,
        )

    def build_target(
        self,
        workspace_id: str,
        repository_id: str,
        action_id: str,
        timeout_seconds: int = 300,
    ) -> BuildExecutionResultView:
        return self._build_service.build_target(
            workspace_id,
            repository_id,
            action_id=action_id,
            timeout_seconds=timeout_seconds,
        )

    def build_project(
        self,
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int = 300,
    ) -> BuildProjectResultView:
        return self._build_service.build_project(
            workspace_id,
            repository_id,
            timeout_seconds=timeout_seconds,
        )

    def find_symbols(
        self,
        workspace_id: str,
        repository_id: str,
        query: str,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        return self._code_service.find_symbols(
            workspace_id,
            repository_id,
            query,
            is_case_sensitive=is_case_sensitive,
            limit=limit,
            offset=offset,
        )

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
        return self._code_service.list_symbols_in_file(
            workspace_id,
            repository_id,
            repository_rel_path,
            query=query,
            is_case_sensitive=is_case_sensitive,
            limit=limit,
            offset=offset,
        )

    def get_file_owner(self, workspace_id: str, repository_id: str, repository_rel_path: str) -> FileOwnerView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            return self._ownership_presenter.file_owner_view(repository.get_file_owner(repository_rel_path))
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc

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
            items = tuple(self._architecture_presenter.file_view(item) for item in repository.list_files_by_owner(owner_id))
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
        return self._code_service.find_definition(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            line=line,
            column=column,
            limit=limit,
            offset=offset,
        )

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
        return self._code_service.find_references(
            workspace_id,
            repository_id,
            include_definition=include_definition,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            line=line,
            column=column,
            limit=limit,
            offset=offset,
        )

    def list_tests(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[TestDefinitionView]:
        return self._test_service.list_tests(workspace_id, repository_id, limit=limit, offset=offset)

    def get_related_tests(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[RelatedTestView]:
        return self._test_service.get_related_tests(
            workspace_id,
            repository_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

    def describe_test_target(self, workspace_id: str, repository_id: str, test_id: str) -> TestTargetDescriptionView:
        return self._test_service.describe_test_target(workspace_id, repository_id, test_id)

    def run_test_targets(
        self,
        workspace_id: str,
        repository_id: str,
        test_ids: tuple[str, ...],
        timeout_seconds: int = 120,
    ) -> RunTestTargetsView:
        return self._test_service.run_test_targets(
            workspace_id,
            repository_id,
            test_ids=test_ids,
            timeout_seconds=timeout_seconds,
        )

    def describe_runner(
        self,
        workspace_id: str,
        repository_id: str,
        runner_id: str,
        file_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> RunnerContextView:
        return self._runner_service.describe_runner(
            workspace_id,
            repository_id,
            runner_id=runner_id,
            file_preview_limit=file_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def run_runner(
        self,
        workspace_id: str,
        repository_id: str,
        runner_id: str,
        timeout_seconds: int = 300,
    ) -> RunnerExecutionResultView:
        return self._runner_service.run_runner(
            workspace_id,
            repository_id,
            runner_id=runner_id,
            timeout_seconds=timeout_seconds,
        )

    def list_quality_providers(self, workspace_id: str, repository_id: str) -> tuple[str, ...]:
        return self._quality_service.list_quality_providers(workspace_id, repository_id)

    def lint_file(self, workspace_id: str, repository_id: str, repository_rel_path: str, provider_id: str, is_fix: bool) -> QualityFileResultView:
        return self._quality_service.lint_file(workspace_id, repository_id, repository_rel_path, provider_id, is_fix)

    def format_file(self, workspace_id: str, repository_id: str, repository_rel_path: str, provider_id: str) -> QualityFileResultView:
        return self._quality_service.format_file(workspace_id, repository_id, repository_rel_path, provider_id)

    def workspace_snapshot(self, workspace_id: str):
        return self._workspace_presenter.workspace_snapshot(self._registry.get_workspace(workspace_id))

    def repository_snapshot(self, workspace_id: str, repository_id: str):
        return self._repository_presenter.repository_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def architecture_snapshot(self, workspace_id: str, repository_id: str) -> ArchitectureSnapshotView:
        return self._architecture_presenter.architecture_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def tests_snapshot(self, workspace_id: str, repository_id: str) -> TestsSnapshotView:
        return self._test_presenter.tests_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def quality_snapshot(self, workspace_id: str, repository_id: str) -> QualitySnapshotView:
        return self._quality_presenter.quality_snapshot(self._registry.get_repository(workspace_id, repository_id))

    def repository_summary(
        self,
        workspace_id: str,
        repository_id: str,
        preview_limit: int = 10,
    ) -> RepositorySummaryView:
        return self._context_service.repository_summary(workspace_id, repository_id, preview_limit=preview_limit)

    def describe_components(
        self,
        workspace_id: str,
        repository_id: str,
        component_ids: tuple[str, ...],
        file_preview_limit: int = 20,
        dependency_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[ComponentContextView, ...]:
        return self._context_service.describe_components(
            workspace_id,
            repository_id,
            component_ids=component_ids,
            file_preview_limit=file_preview_limit,
            dependency_preview_limit=dependency_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def describe_files(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_paths: tuple[str, ...],
        symbol_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[FileContextView, ...]:
        return self._context_service.describe_files(
            workspace_id,
            repository_id,
            repository_rel_paths=repository_rel_paths,
            symbol_preview_limit=symbol_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def describe_symbol_context(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str,
        reference_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> SymbolContextView:
        return self._context_service.describe_symbol_context(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def get_component_dependencies(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[DependencyRefView]:
        return self._architecture_service.get_component_dependencies(
            workspace_id,
            repository_id,
            component_id,
            limit=limit,
            offset=offset,
        )

    def list_component_dependency_edges(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ComponentDependencyEdgeView]:
        return self._architecture_service.list_component_dependency_edges(
            workspace_id,
            repository_id,
            component_id=component_id,
            limit=limit,
            offset=offset,
        )

    def get_component_dependents(
        self,
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[str]:
        return self._architecture_service.get_component_dependents(
            workspace_id,
            repository_id,
            component_id,
            limit=limit,
            offset=offset,
        )

    def analyze_impact(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        reference_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 20,
    ) -> ImpactSummaryView:
        return self._context_service.analyze_impact(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def analyze_change(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        reference_preview_limit: int = 50,
        dependent_preview_limit: int = 50,
        test_preview_limit: int = 25,
        runner_preview_limit: int = 25,
    ) -> ChangeImpactView:
        return self._context_service.analyze_change(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
            runner_preview_limit=runner_preview_limit,
        )
