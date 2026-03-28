from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.core.change_models import ChangeTarget
from suitcode.core.repository import Repository
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.validation import validate_preview_limit
from suitcode.core.validation import validate_change_preview_limit
from suitcode.core.workspace import Workspace
from suitcode.mcp.errors import McpNotFoundError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.models import (
    ActionAvailabilityView,
    AddRepositoryResult,
    AggregatorView,
    ActionView,
    ArchitectureSnapshotView,
    BuildExecutionResultView,
    BuildProjectResultView,
    BuildTargetDescriptionView,
    BatchChangeImpactTargetView,
    BatchChangeImpactView,
    BatchMinimumVerifiedChangeSetTargetView,
    BatchMinimumVerifiedChangeSetView,
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
    FileUnderstandingTargetView,
    FileUnderstandingView,
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
    RepositoryUnderstandingView,
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
    WorkspacesResourceView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.service_runtime import build_mcp_service_runtime
from suitcode.mcp.state import WorkspaceRegistry

T = TypeVar("T")


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

    def workspaces_resource_view(self, limit: int | None = None, offset: int = 0) -> WorkspacesResourceView:
        listing = self.list_workspaces(limit=limit, offset=offset)
        return self._workspace_presenter.workspaces_resource_view(
            listing.items,
            limit=listing.limit,
            offset=listing.offset,
            total=listing.total,
            truncated=listing.truncated,
            next_offset=listing.next_offset,
        )

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

    def repository_summary_by_path(
        self,
        repository_path: str,
        preview_limit: int = 10,
    ) -> RepositorySummaryView:
        validate_preview_limit(preview_limit, "preview_limit", max_value=50, error_cls=McpValidationError)

        def _callback(repository: Repository) -> RepositorySummaryView:
            return self._repository_summary_presenter.summary_view(repository, preview_limit)

        return self._with_read_only_repository(repository_path, _callback)

    def understand_repository(
        self,
        repository_path: str,
        preview_limit: int = 10,
    ) -> RepositoryUnderstandingView:
        validate_preview_limit(preview_limit, "preview_limit", max_value=50, error_cls=McpValidationError)

        def _callback(repository: Repository) -> RepositoryUnderstandingView:
            summary = self._repository_summary_presenter.summary_view(repository, preview_limit)
            truth_coverage = self._intelligence_presenter.truth_coverage_summary_view(repository.get_truth_coverage())
            return RepositoryUnderstandingView(
                repository=summary,
                truth_coverage=truth_coverage,
                recommended_next_questions=(
                    "who_owns_this",
                    "what_changes_if_i_edit_this",
                    "what_should_i_run",
                    "can_i_do_this",
                ),
                provenance=self._merge_view_provenance(summary.provenance, truth_coverage.provenance),
            )

        return self._with_read_only_repository(repository_path, _callback)

    def understand_file(
        self,
        repository_path: str,
        repository_rel_paths: tuple[str, ...],
        related_test_limit: int = 10,
    ) -> FileUnderstandingView:
        validate_preview_limit(related_test_limit, "related_test_limit", max_value=25, error_cls=McpValidationError)

        def _callback(repository: Repository) -> FileUnderstandingView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets = tuple(
                self._understand_file_target(repository, repository_rel_path, related_test_limit=related_test_limit)
                for repository_rel_path in normalized_paths
            )
            return FileUnderstandingView(
                target_count=len(targets),
                targets=targets,
                owner_ids=tuple(sorted({item.file_owner.owner.id for item in targets})),
                aggregate_dependency_file_count=len(
                    {item.path for target in targets for item in target.dependency_files_preview}
                ),
                aggregate_dependency_files_preview=self._dedupe_views(
                    tuple(item for target in targets for item in target.dependency_files_preview),
                    key=lambda item: item.path,
                ),
                aggregate_dependent_file_count=len(
                    {item.path for target in targets for item in target.dependent_files_preview}
                ),
                aggregate_dependent_files_preview=self._dedupe_views(
                    tuple(item for target in targets for item in target.dependent_files_preview),
                    key=lambda item: item.path,
                ),
                aggregate_related_tests=self._dedupe_views(
                    tuple(item for target in targets for item in target.related_tests),
                    key=lambda item: item.id,
                ),
                suggested_follow_ups=(
                    tuple()
                    if targets and all(target.structured_artifact is not None for target in targets)
                    else (
                        "what_changes_if_i_edit_this",
                        "what_should_i_run",
                        "can_i_do_this",
                    )
                ),
                provenance=self._merge_view_provenance(
                    *(target.provenance for target in targets),
                ),
            )

        return self._with_read_only_repository(repository_path, _callback)

    def get_file_owner_by_path(self, repository_path: str, repository_rel_path: str) -> FileOwnerView:
        def _callback(repository: Repository) -> FileOwnerView:
            try:
                return self._ownership_presenter.file_owner_view(repository.get_file_owner(repository_rel_path))
            except ValueError as exc:
                raise McpNotFoundError(
                    self._explain_unowned_file_error(
                        repository,
                        repository_rel_path,
                        str(exc),
                        tool_name="get_file_owner_by_path",
                    )
                ) from exc

        return self._with_read_only_repository(repository_path, _callback)

    def get_related_tests_by_path(
        self,
        repository_path: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[RelatedTestView]:
        def _callback(repository: Repository) -> ListResult[RelatedTestView]:
            try:
                items = tuple(
                    self._test_presenter.related_test_view(item)
                    for item in repository.tests.get_related_tests(
                        RelatedTestTarget(repository_rel_path=repository_rel_path, owner_id=owner_id)
                    )
                )
                return self._pagination.paginate(items, limit, offset)
            except ValueError as exc:
                raise McpValidationError(str(exc)) from exc

        return self._with_read_only_repository(repository_path, _callback)

    def what_changes_if_i_edit_this(
        self,
        repository_path: str,
        repository_rel_paths: tuple[str, ...],
        reference_preview_limit: int = 50,
        dependent_preview_limit: int = 50,
        test_preview_limit: int = 25,
        runner_preview_limit: int = 25,
    ) -> BatchChangeImpactView:
        validate_change_preview_limit(reference_preview_limit, "reference_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(dependent_preview_limit, "dependent_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(test_preview_limit, "test_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(runner_preview_limit, "runner_preview_limit", error_cls=McpValidationError)

        def _callback(repository: Repository) -> BatchChangeImpactView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets: list[BatchChangeImpactTargetView] = []
            for repository_rel_path in normalized_paths:
                try:
                    impact = repository.analyze_change(
                        ChangeTarget(repository_rel_path=repository_rel_path),
                        reference_preview_limit=reference_preview_limit,
                        dependent_preview_limit=dependent_preview_limit,
                        test_preview_limit=test_preview_limit,
                        runner_preview_limit=runner_preview_limit,
                    )
                except ValueError as exc:
                    raise McpValidationError(str(exc)) from exc
                targets.append(
                    BatchChangeImpactTargetView(
                        repository_rel_path=repository_rel_path,
                        impact=self._change_impact_presenter.change_impact_view(impact),
                    )
                )
            frozen_targets = tuple(targets)
            return BatchChangeImpactView(
                target_count=len(frozen_targets),
                targets=frozen_targets,
                owner_ids=tuple(sorted({item.impact.owner.id for item in frozen_targets})),
                dependent_files=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.dependent_files),
                    key=lambda item: item.path,
                ),
                dependent_components=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.dependent_components),
                    key=lambda item: item.id,
                ),
                reference_locations=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.reference_locations),
                    key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                ),
                related_tests=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.related_tests),
                    key=lambda item: item.test.id,
                ),
                related_runners=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.related_runners),
                    key=lambda item: item.runner.id,
                ),
                quality_gates=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.impact.quality_gates),
                    key=lambda item: (item.provider_id, item.reason, item.applies),
                ),
                provenance=self._merge_view_provenance(*(target.impact.provenance for target in frozen_targets)),
            )

        return self._with_read_only_repository(repository_path, _callback)

    def get_minimum_verified_change_set_by_path(
        self,
        repository_path: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
    ) -> MinimumVerifiedChangeSetView:
        def _callback(repository: Repository) -> MinimumVerifiedChangeSetView:
            try:
                target = ChangeTarget(
                    symbol_id=symbol_id,
                    repository_rel_path=repository_rel_path,
                    owner_id=owner_id,
                )
                change_set = repository.get_minimum_verified_change_set(target)
                return self._change_impact_presenter.minimum_verified_change_set_view(change_set)
            except ValueError as exc:
                raise McpValidationError(str(exc)) from exc

        return self._with_read_only_repository(repository_path, _callback)

    def what_should_i_run(
        self,
        repository_path: str,
        repository_rel_paths: tuple[str, ...],
    ) -> BatchMinimumVerifiedChangeSetView:
        def _callback(repository: Repository) -> BatchMinimumVerifiedChangeSetView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets: list[BatchMinimumVerifiedChangeSetTargetView] = []
            for repository_rel_path in normalized_paths:
                try:
                    change_set = repository.get_minimum_verified_change_set(
                        ChangeTarget(repository_rel_path=repository_rel_path)
                    )
                except ValueError as exc:
                    raise McpValidationError(str(exc)) from exc
                targets.append(
                    BatchMinimumVerifiedChangeSetTargetView(
                        repository_rel_path=repository_rel_path,
                        change_set=self._change_impact_presenter.minimum_verified_change_set_view(change_set),
                    )
                )
            frozen_targets = tuple(targets)
            return BatchMinimumVerifiedChangeSetView(
                target_count=len(frozen_targets),
                targets=frozen_targets,
                owner_ids=tuple(sorted({item.change_set.owner.id for item in frozen_targets})),
                tests=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.tests),
                    key=lambda item: item.test_id,
                ),
                build_targets=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.build_targets),
                    key=lambda item: item.action_id,
                ),
                runner_actions=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.runner_actions),
                    key=lambda item: item.action_id,
                ),
                quality_validation_operations=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.quality_validation_operations),
                    key=lambda item: item.id,
                ),
                quality_hygiene_operations=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.quality_hygiene_operations),
                    key=lambda item: item.id,
                ),
                excluded_items=self._dedupe_views(
                    tuple(item for target in frozen_targets for item in target.change_set.excluded_items),
                    key=lambda item: (item.item_kind, item.item_id, item.reason_code),
                ),
                provenance=self._merge_view_provenance(*(target.change_set.provenance for target in frozen_targets)),
            )

        return self._with_read_only_repository(repository_path, _callback)

    def can_i_do_this(
        self,
        repository_path: str,
        repository_rel_path: str,
        requested_action_kind: str,
    ) -> ActionAvailabilityView:
        allowed_action_kinds = {
            "test",
            "build",
            "runner",
            "quality_validation",
            "quality_hygiene",
        }
        normalized_action_kind = requested_action_kind.strip().lower()
        if normalized_action_kind not in allowed_action_kinds:
            raise McpValidationError(
                "requested_action_kind must be one of: build, quality_hygiene, quality_validation, runner, test"
            )

        def _callback(repository: Repository) -> ActionAvailabilityView:
            target = ChangeTarget(repository_rel_path=repository_rel_path)
            truth_coverage = self._intelligence_presenter.truth_coverage_summary_view(
                repository.get_change_truth_coverage(target)
            )
            owner = self._ownership_presenter.owner_view(repository.get_file_owner(repository_rel_path).owner)
            primary_component = None
            minimum_verified = None
            available_action_kinds: tuple[str, ...] = tuple()
            try:
                change_set = repository.get_minimum_verified_change_set(target)
                minimum_verified = self._change_impact_presenter.minimum_verified_change_set_view(change_set)
                primary_component = minimum_verified.primary_component
                kinds: list[str] = []
                if minimum_verified.tests:
                    kinds.append("test")
                if minimum_verified.build_targets:
                    kinds.append("build")
                if minimum_verified.runner_actions:
                    kinds.append("runner")
                if minimum_verified.quality_validation_operations:
                    kinds.append("quality_validation")
                if minimum_verified.quality_hygiene_operations:
                    kinds.append("quality_hygiene")
                available_action_kinds = tuple(sorted(kinds))
            except ValueError as exc:
                if "no deterministic validation surfaces were found" not in str(exc):
                    raise McpValidationError(str(exc)) from exc

            actions_domain = next((item for item in truth_coverage.domains if item.domain == "actions"), None)
            actions_available = actions_domain is not None and actions_domain.availability == "available"
            supported = normalized_action_kind in available_action_kinds
            if supported:
                reason_code = "available"
            elif not actions_available:
                reason_code = "actions_truth_unavailable"
            elif available_action_kinds:
                reason_code = "requested_kind_not_in_minimum_verified_set"
            else:
                reason_code = "no_deterministic_actions_available"

            provenance_groups = [truth_coverage.provenance]
            if minimum_verified is not None:
                provenance_groups.append(minimum_verified.provenance)

            return ActionAvailabilityView(
                requested_action_kind=normalized_action_kind,
                supported=supported,
                reason_code=reason_code,
                available_action_kinds=available_action_kinds,
                owner=owner,
                primary_component=primary_component,
                recommended_tests=(minimum_verified.tests if minimum_verified is not None else tuple()),
                recommended_build_targets=(minimum_verified.build_targets if minimum_verified is not None else tuple()),
                recommended_runner_actions=(minimum_verified.runner_actions if minimum_verified is not None else tuple()),
                recommended_quality_validation_operations=(
                    minimum_verified.quality_validation_operations if minimum_verified is not None else tuple()
                ),
                recommended_quality_hygiene_operations=(
                    minimum_verified.quality_hygiene_operations if minimum_verified is not None else tuple()
                ),
                truth_coverage=truth_coverage,
                provenance=self._merge_view_provenance(*provenance_groups),
            )

        return self._with_read_only_repository(repository_path, _callback)

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
            raise McpNotFoundError(
                self._explain_unowned_file_error(repository, repository_rel_path, str(exc), tool_name="get_file_owner")
            ) from exc

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

    def _understand_file_target(
        self,
        repository: Repository,
        repository_rel_path: str,
        *,
        related_test_limit: int,
    ) -> FileUnderstandingTargetView:
        try:
            context = repository.describe_files((repository_rel_path,), symbol_preview_limit=20, test_preview_limit=related_test_limit)[0]
            owner = self._ownership_presenter.file_owner_view(repository.get_file_owner(repository_rel_path))
            dependency_files_preview = tuple(
                self._intelligence_presenter.file_relationship_view(item) for item in context.dependency_files_preview
            )
            dependent_files_preview = tuple(
                self._intelligence_presenter.file_relationship_view(item) for item in context.dependent_files_preview
            )
            related_tests = tuple(
                self._test_presenter.related_test_view(item)
                for item in repository.tests.get_related_tests(
                    RelatedTestTarget(repository_rel_path=repository_rel_path)
                )[:related_test_limit]
            )
            structured_artifact = repository.describe_structured_artifact(repository_rel_path)
            structured_artifact_view = (
                self._intelligence_presenter.structured_artifact_view(structured_artifact)
                if structured_artifact is not None
                else None
            )
        except ValueError as exc:
            raise McpValidationError(
                self._explain_unowned_file_error(repository, repository_rel_path, str(exc), tool_name="understand_file")
            ) from exc
        return FileUnderstandingTargetView(
            repository_rel_path=repository_rel_path,
            file_owner=owner,
            dependency_file_count=context.dependency_file_count,
            dependency_files_preview=dependency_files_preview,
            dependent_file_count=context.dependent_file_count,
            dependent_files_preview=dependent_files_preview,
            related_tests=related_tests,
            structured_artifact=structured_artifact_view,
            provenance=self._merge_view_provenance(
                owner.file.provenance,
                *(item.provenance for item in dependency_files_preview),
                *(item.provenance for item in dependent_files_preview),
                *(item.provenance for item in related_tests),
                structured_artifact_view.provenance if structured_artifact_view is not None else tuple(),
            ),
        )

    @staticmethod
    def _validate_repository_rel_paths(
        repository_rel_paths: tuple[str, ...] | str,
        *,
        field_name: str,
    ) -> tuple[str, ...]:
        if isinstance(repository_rel_paths, str):
            repository_rel_paths = (repository_rel_paths,)
        if not repository_rel_paths:
            raise McpValidationError(f"{field_name} must not be empty")
        normalized = tuple(item.strip() for item in repository_rel_paths)
        if any(not item for item in normalized):
            raise McpValidationError(f"{field_name} must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise McpValidationError(f"{field_name} must not contain duplicates")
        return normalized

    @staticmethod
    def _dedupe_views(items: tuple[T, ...], *, key: Callable[[T], object]) -> tuple[T, ...]:
        deduped: list[T] = []
        seen: set[object] = set()
        for item in items:
            item_key = key(item)
            if item_key in seen:
                continue
            seen.add(item_key)
            deduped.append(item)
        return tuple(deduped)

    def _with_read_only_repository(
        self,
        repository_path: str,
        callback: Callable[[Repository], T],
    ) -> T:
        try:
            workspace = Workspace(Path(repository_path), materialize_suit_dir=False)
            repository = workspace.repositories[0]
            return callback(repository)
        except (McpNotFoundError, McpValidationError, McpUnsupportedRepositoryError):
            raise
        except ValueError as exc:
            message = str(exc)
            if "No registered providers matched" in message or "unsupported repository" in message:
                raise McpUnsupportedRepositoryError(message) from exc
            if "does not exist" in message or "is not a directory" in message:
                raise McpValidationError(message) from exc
            raise McpValidationError(message) from exc

    @staticmethod
    def _merge_view_provenance(*groups) -> tuple:
        merged = []
        seen: set[str] = set()
        for group in groups:
            for entry in group:
                key = entry.model_dump_json()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(entry)
        return tuple(merged)

    @staticmethod
    def _explain_unowned_file_error(
        repository: Repository,
        repository_rel_path: str,
        message: str,
        *,
        tool_name: str,
    ) -> str:
        if "unknown repository file owner" not in message:
            return message
        candidate = (repository.root / repository_rel_path.strip().replace("\\", "/").removeprefix("./")).resolve()
        try:
            candidate.relative_to(repository.root)
        except ValueError:
            return message
        if not candidate.exists() or not candidate.is_file():
            return message
        return (
            f"{message}. `{tool_name}` currently supports only provider-owned files. "
            "Files that exist in the repository but are not deterministically owned by a registered provider, "
            "including unsupported plain-text or documentation artifacts, are not supported by this tool."
        )
