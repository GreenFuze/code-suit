from __future__ import annotations

from pathlib import Path

from suitcode.analytics.recorder import ToolCallRecorder
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
    CloseWorkspaceResult,
    AnalyticsSummaryView,
    BenchmarkReportView,
    ComponentDependencyEdgeView,
    ComponentContextView,
    ComponentView,
    DependencyRefView,
    ExternalPackageView,
    FileContextView,
    FileOwnerView,
    FileView,
    ImpactSummaryView,
    InefficientToolCallView,
    ListResult,
    LocationView,
    OpenWorkspaceResult,
    PackageManagerView,
    ProviderDescriptorView,
    QualityFileResultView,
    QualityProvidersView,
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
    ToolUsageAnalyticsView,
    TestsSnapshotView,
    MinimumVerifiedChangeSetView,
    TestDefinitionView,
    TestTargetDescriptionView,
    TruthCoverageSummaryView,
    WorkspaceView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.service_runtime import build_mcp_service_runtime
from suitcode.mcp.state import WorkspaceRegistry


class SuitMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry | None = None,
        pagination: PaginationPolicy | None = None,
    ) -> None:
        self._registry = registry or WorkspaceRegistry()
        self._pagination = pagination or PaginationPolicy()
        runtime = build_mcp_service_runtime(
            registry=self._registry,
            pagination=self._pagination,
        )
        self._provider_presenter = runtime.provider_presenter
        self._workspace_presenter = runtime.workspace_presenter
        self._repository_presenter = runtime.repository_presenter
        self._architecture_presenter = runtime.architecture_presenter
        self._action_presenter = runtime.action_presenter
        self._build_presenter = runtime.build_presenter
        self._code_presenter = runtime.code_presenter
        self._test_presenter = runtime.test_presenter
        self._runner_presenter = runtime.runner_presenter
        self._quality_presenter = runtime.quality_presenter
        self._ownership_presenter = runtime.ownership_presenter
        self._repository_summary_presenter = runtime.repository_summary_presenter
        self._intelligence_presenter = runtime.intelligence_presenter
        self._change_impact_presenter = runtime.change_impact_presenter
        self._analytics_presenter = runtime.analytics_presenter
        self._analytics_settings = runtime.analytics_settings
        self._analytics_store = runtime.analytics_store
        self._analytics_recorder = runtime.analytics_recorder
        self._analytics_aggregator = runtime.analytics_aggregator
        self._workspace_service = runtime.workspace_service
        self._architecture_service = runtime.architecture_service
        self._action_service = runtime.action_service
        self._code_service = runtime.code_service
        self._build_service = runtime.build_service
        self._test_service = runtime.test_service
        self._quality_service = runtime.quality_service
        self._runner_service = runtime.runner_service
        self._context_service = runtime.context_service
        self._analytics_service = runtime.analytics_service

    def list_supported_providers(self, limit: int | None = None, offset: int = 0) -> ListResult[ProviderDescriptorView]:
        return self._workspace_service.list_supported_providers(limit=limit, offset=offset)

    def inspect_repository_support(self, repository_path: str) -> RepositorySupportView:
        return self._workspace_service.inspect_repository_support(repository_path)

    def open_workspace(self, repository_path: str) -> OpenWorkspaceResult:
        return self._workspace_service.open_workspace(repository_path)

    def list_workspaces(self, limit: int | None = None, offset: int = 0) -> ListResult[WorkspaceView]:
        return self._workspace_service.list_workspaces(limit=limit, offset=offset)

    def list_open_workspaces(self, limit: int | None = None, offset: int = 0) -> ListResult[WorkspaceView]:
        return self.list_workspaces(limit=limit, offset=offset)

    def get_workspace(self, workspace_id: str) -> WorkspaceView:
        return self._workspace_service.get_workspace(workspace_id)

    def close_workspace(self, workspace_id: str) -> None:
        self._workspace_service.close_workspace(workspace_id)

    def close_workspace_result(self, workspace_id: str) -> CloseWorkspaceResult:
        self.close_workspace(workspace_id)
        return CloseWorkspaceResult(workspace_id=workspace_id, closed=True)

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

    def list_quality_providers_view(self, workspace_id: str, repository_id: str) -> QualityProvidersView:
        return QualityProvidersView(provider_ids=self.list_quality_providers(workspace_id, repository_id))

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

    def get_analytics_summary(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
    ) -> AnalyticsSummaryView:
        return self._analytics_service.get_analytics_summary(
            workspace_id=workspace_id,
            repository_id=repository_id,
            include_global=include_global,
            session_id=session_id,
        )

    def get_tool_usage_analytics(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ToolUsageAnalyticsView]:
        return self._analytics_service.get_tool_usage_analytics(
            workspace_id=workspace_id,
            repository_id=repository_id,
            include_global=include_global,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )

    def get_inefficient_tool_calls(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[InefficientToolCallView]:
        return self._analytics_service.get_inefficient_tool_calls(
            workspace_id=workspace_id,
            repository_id=repository_id,
            include_global=include_global,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )

    def get_mcp_benchmark_report(self) -> BenchmarkReportView:
        return self._analytics_service.get_mcp_benchmark_report()

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

    def get_minimum_verified_change_set(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
    ) -> MinimumVerifiedChangeSetView:
        return self._context_service.get_minimum_verified_change_set(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
        )

    def get_truth_coverage(
        self,
        workspace_id: str,
        repository_id: str,
    ) -> TruthCoverageSummaryView:
        return self._context_service.get_truth_coverage(
            workspace_id,
            repository_id,
        )

    @property
    def analytics_recorder(self) -> ToolCallRecorder:
        return self._analytics_recorder

    def resolve_analytics_repository_root(self, arguments: dict[str, object]) -> Path | None:
        workspace_id = arguments.get("workspace_id")
        repository_id = arguments.get("repository_id")
        if isinstance(workspace_id, str) and isinstance(repository_id, str):
            try:
                return self._registry.get_repository(workspace_id, repository_id).root
            except Exception:  # noqa: BLE001
                return None

        repository_path = arguments.get("repository_path")
        if isinstance(repository_path, str):
            try:
                from suitcode.core.repository import Repository

                return Repository.root_candidate(Path(repository_path))
            except Exception:  # noqa: BLE001
                return None
        return None
