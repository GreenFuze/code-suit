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
    BatchChangeImpactCompactTargetView,
    BatchChangeImpactCompactView,
    BatchChangeImpactStandardTargetView,
    BatchChangeImpactStandardView,
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
    ExcludedMinimumVerifiedItemView,
    ExternalPackageView,
    FileContextView,
    FileOwnerView,
    FileUnderstandingTargetView,
    FileUnderstandingView,
    FileUnderstandingCompactTargetView,
    FileUnderstandingCompactView,
    FileUnderstandingStandardTargetView,
    FileUnderstandingStandardView,
    FileView,
    ImpactSummaryView,
    InefficientToolCallView,
    ListResult,
    LocationView,
    MinimumVerifiedBuildTargetView,
    MinimumVerifiedTestTargetView,
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
        detail_level: str = "compact",
    ) -> FileUnderstandingCompactView | FileUnderstandingStandardView | FileUnderstandingView:
        validate_preview_limit(related_test_limit, "related_test_limit", max_value=25, error_cls=McpValidationError)
        validated_detail_level = self._validate_detail_level(detail_level)

        def _callback(repository: Repository) -> FileUnderstandingCompactView | FileUnderstandingStandardView | FileUnderstandingView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets = tuple(
                self._understand_file_target(
                    repository,
                    repository_rel_path,
                    related_test_limit=self._detail_preview_limit(validated_detail_level, related_test_limit),
                    detail_level=validated_detail_level,
                )
                for repository_rel_path in normalized_paths
            )
            if validated_detail_level == "compact":
                return self._compact_file_understanding_view(targets)
            if validated_detail_level == "standard":
                return self._standard_file_understanding_view(targets)
            aggregate_reference_site_count, aggregate_reference_sites_preview = self._aggregate_ranked_views(
                tuple(target.reference_sites_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                rank_key=self._location_rank_key,
            )
            aggregate_dependency_file_count, aggregate_dependency_files_preview = self._aggregate_ranked_views(
                tuple(target.dependency_files_preview for target in targets),
                key=lambda item: item.path,
                rank_key=self._file_relationship_rank_key,
            )
            aggregate_dependent_file_count, aggregate_dependent_files_preview = self._aggregate_ranked_views(
                tuple(target.dependent_files_preview for target in targets),
                key=lambda item: item.path,
                rank_key=self._file_relationship_rank_key,
            )
            aggregate_render_child_count, aggregate_render_children_preview = self._aggregate_ranked_views(
                tuple(target.render_children_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
                rank_key=self._render_edge_rank_key,
            )
            aggregate_render_parent_count, aggregate_render_parents_preview = self._aggregate_ranked_views(
                tuple(target.render_parents_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
                rank_key=self._render_edge_rank_key,
            )
            aggregate_invariant_finding_count, aggregate_invariant_findings_preview = self._aggregate_ranked_views(
                tuple(target.invariant_findings_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
                rank_key=self._invariant_rank_key,
            )
            aggregate_local_flow_edge_count, aggregate_local_flow_edges_preview = self._aggregate_ranked_views(
                tuple(target.local_flow_edges_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
                rank_key=self._static_flow_rank_key,
            )
            aggregate_implementation_location_count, aggregate_implementation_locations_preview = self._aggregate_ranked_views(
                tuple(target.implementation_locations_preview for target in targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                rank_key=self._location_rank_key,
            )
            _, aggregate_related_tests = self._aggregate_ranked_views(
                tuple(target.related_tests for target in targets),
                key=lambda item: item.id,
                rank_key=self._related_test_rank_key,
            )
            return FileUnderstandingView(
                detail_level="full",
                target_count=len(targets),
                targets=targets,
                owner_ids=tuple(sorted({item.file_owner.owner.id for item in targets})),
                aggregate_reference_site_count=aggregate_reference_site_count,
                aggregate_reference_sites_preview=aggregate_reference_sites_preview,
                aggregate_dependency_file_count=aggregate_dependency_file_count,
                aggregate_dependency_files_preview=aggregate_dependency_files_preview,
                aggregate_dependent_file_count=aggregate_dependent_file_count,
                aggregate_dependent_files_preview=aggregate_dependent_files_preview,
                aggregate_render_child_count=aggregate_render_child_count,
                aggregate_render_children_preview=aggregate_render_children_preview,
                aggregate_render_parent_count=aggregate_render_parent_count,
                aggregate_render_parents_preview=aggregate_render_parents_preview,
                aggregate_invariant_finding_count=aggregate_invariant_finding_count,
                aggregate_invariant_findings_preview=aggregate_invariant_findings_preview,
                aggregate_local_flow_edge_count=aggregate_local_flow_edge_count,
                aggregate_local_flow_edges_preview=aggregate_local_flow_edges_preview,
                aggregate_implementation_location_count=aggregate_implementation_location_count,
                aggregate_implementation_locations_preview=aggregate_implementation_locations_preview,
                aggregate_related_tests=aggregate_related_tests,
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
        detail_level: str = "compact",
    ) -> BatchChangeImpactCompactView | BatchChangeImpactStandardView | BatchChangeImpactView:
        validate_change_preview_limit(reference_preview_limit, "reference_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(dependent_preview_limit, "dependent_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(test_preview_limit, "test_preview_limit", error_cls=McpValidationError)
        validate_change_preview_limit(runner_preview_limit, "runner_preview_limit", error_cls=McpValidationError)
        validated_detail_level = self._validate_detail_level(detail_level)

        def _callback(repository: Repository) -> BatchChangeImpactCompactView | BatchChangeImpactStandardView | BatchChangeImpactView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets: list[BatchChangeImpactTargetView] = []
            for repository_rel_path in normalized_paths:
                try:
                    impact = repository.analyze_change(
                        ChangeTarget(repository_rel_path=repository_rel_path),
                        reference_preview_limit=self._detail_preview_limit(validated_detail_level, reference_preview_limit),
                        dependent_preview_limit=self._detail_preview_limit(validated_detail_level, dependent_preview_limit),
                        test_preview_limit=self._detail_preview_limit(validated_detail_level, test_preview_limit),
                        runner_preview_limit=self._detail_preview_limit(validated_detail_level, runner_preview_limit),
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
            if validated_detail_level == "compact":
                return self._compact_change_impact_view(frozen_targets)
            if validated_detail_level == "standard":
                return self._standard_change_impact_view(frozen_targets)
            _, reference_sites = self._aggregate_ranked_views(
                tuple(target.impact.reference_locations for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                rank_key=self._location_rank_key,
            )
            _, dependent_files = self._aggregate_ranked_views(
                tuple(target.impact.dependent_files for target in frozen_targets),
                key=lambda item: item.path,
                rank_key=self._file_relationship_rank_key,
            )
            _, render_children = self._aggregate_ranked_views(
                tuple(target.impact.render_children for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
                rank_key=self._render_edge_rank_key,
            )
            _, render_parents = self._aggregate_ranked_views(
                tuple(target.impact.render_parents for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
                rank_key=self._render_edge_rank_key,
            )
            _, invariant_findings = self._aggregate_ranked_views(
                tuple(target.impact.invariant_findings for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
                rank_key=self._invariant_rank_key,
            )
            _, local_flow_edges = self._aggregate_ranked_views(
                tuple(target.impact.local_flow_edges for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
                rank_key=self._static_flow_rank_key,
            )
            _, implementation_locations = self._aggregate_ranked_views(
                tuple(target.impact.implementation_locations for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                rank_key=self._location_rank_key,
            )
            _, implementation_components = self._aggregate_ranked_views(
                tuple(target.impact.implementation_components for target in frozen_targets),
                key=lambda item: item.id,
                rank_key=self._component_rank_key,
            )
            _, dependent_components = self._aggregate_ranked_views(
                tuple(target.impact.dependent_components for target in frozen_targets),
                key=lambda item: item.id,
                rank_key=self._component_rank_key,
            )
            _, reference_locations = self._aggregate_ranked_views(
                tuple(target.impact.reference_locations for target in frozen_targets),
                key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
                rank_key=self._location_rank_key,
            )
            _, related_tests = self._aggregate_ranked_views(
                tuple(target.impact.related_tests for target in frozen_targets),
                key=lambda item: item.test.id,
                rank_key=self._test_impact_rank_key,
            )
            _, related_runners = self._aggregate_ranked_views(
                tuple(target.impact.related_runners for target in frozen_targets),
                key=lambda item: item.runner.id,
                rank_key=self._runner_impact_rank_key,
            )
            _, quality_gates = self._aggregate_ranked_views(
                tuple(target.impact.quality_gates for target in frozen_targets),
                key=lambda item: (item.provider_id, item.reason, item.applies),
                rank_key=self._quality_gate_rank_key,
            )
            return BatchChangeImpactView(
                detail_level="full",
                target_count=len(frozen_targets),
                targets=frozen_targets,
                owner_ids=tuple(sorted({item.impact.owner.id for item in frozen_targets})),
                reference_sites=reference_sites,
                dependent_files=dependent_files,
                render_children=render_children,
                render_parents=render_parents,
                invariant_findings=invariant_findings,
                local_flow_edges=local_flow_edges,
                implementation_locations=implementation_locations,
                implementation_components=implementation_components,
                dependent_components=dependent_components,
                reference_locations=reference_locations,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
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
            tests = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.tests),
                key=lambda item: item.test_id,
            )
            build_targets = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.build_targets),
                key=lambda item: item.action_id,
            )
            runner_actions = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.runner_actions),
                key=lambda item: item.action_id,
            )
            quality_validation_operations = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.quality_validation_operations),
                key=lambda item: item.id,
            )
            quality_hygiene_operations = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.quality_hygiene_operations),
                key=lambda item: item.id,
            )
            excluded_items = self._dedupe_views(
                tuple(item for target in frozen_targets for item in target.change_set.excluded_items),
                key=lambda item: (item.item_kind, item.item_id, item.reason_code),
            )
            tests, excluded_items = self._narrow_batch_minimum_verified_tests(
                tests=tests,
                build_targets=build_targets,
                excluded_items=excluded_items,
            )
            excluded_items = self._filter_batch_minimum_verified_exclusions(excluded_items)
            return BatchMinimumVerifiedChangeSetView(
                compact_summary=self._change_impact_presenter.minimum_verified_compact_summary_view(
                    tests=tests,
                    build_targets=build_targets,
                    runner_actions=runner_actions,
                    quality_validation_operations=quality_validation_operations,
                    quality_hygiene_operations=quality_hygiene_operations,
                    excluded_items=excluded_items,
                ),
                target_count=len(frozen_targets),
                targets=frozen_targets,
                owner_ids=tuple(sorted({item.change_set.owner.id for item in frozen_targets})),
                tests=tests,
                build_targets=build_targets,
                runner_actions=runner_actions,
                quality_validation_operations=quality_validation_operations,
                quality_hygiene_operations=quality_hygiene_operations,
                excluded_items=excluded_items,
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
        detail_level: str,
    ) -> FileUnderstandingTargetView:
        try:
            context = repository.describe_files((repository_rel_path,), symbol_preview_limit=20, test_preview_limit=related_test_limit)[0]
            owner = self._ownership_presenter.file_owner_view(repository.get_file_owner(repository_rel_path))
            reference_sites_preview = tuple(
                self._code_presenter.location_view(item) for item in context.reference_sites_preview
            )
            dependency_files_preview = tuple(
                self._intelligence_presenter.file_relationship_view(item) for item in context.dependency_files_preview
            )
            dependent_files_preview = tuple(
                self._intelligence_presenter.file_relationship_view(item) for item in context.dependent_files_preview
            )
            render_children_preview = tuple(
                self._intelligence_presenter.render_edge_view(item) for item in context.render_children_preview
            )
            render_parents_preview = tuple(
                self._intelligence_presenter.render_edge_view(item) for item in context.render_parents_preview
            )
            invariant_findings_preview = tuple(
                self._intelligence_presenter.invariant_finding_view(item) for item in context.invariant_findings_preview
            )
            local_flow_edges_preview = tuple(
                self._intelligence_presenter.static_flow_edge_view(item) for item in context.local_flow_edges_preview
            )
            if detail_level == "compact":
                invariant_findings_preview = self._compact_invariant_findings(invariant_findings_preview)
            implementation_locations_preview = tuple(
                self._code_presenter.location_view(item) for item in context.implementation_locations_preview
            )
            related_tests = tuple(
                self._test_presenter.related_test_view(item)
                for item in repository.tests.get_related_tests(
                    RelatedTestTarget(repository_rel_path=repository_rel_path)
                )[:related_test_limit]
            )
            structured_artifact = repository.describe_structured_artifact(repository_rel_path)
            structured_artifact_view = (
                self._shape_structured_artifact_view(
                    self._intelligence_presenter.structured_artifact_view(structured_artifact),
                    detail_level=detail_level,
                )
                if structured_artifact is not None
                else None
            )
        except ValueError as exc:
            raise McpValidationError(
                self._explain_unowned_file_error(repository, repository_rel_path, str(exc), tool_name="understand_file")
            ) from exc
        return FileUnderstandingTargetView(
            detail_level="full",
            repository_rel_path=repository_rel_path,
            file_owner=owner,
            reference_site_count=context.reference_site_count,
            reference_sites_preview=reference_sites_preview,
            dependency_file_count=context.dependency_file_count,
            dependency_files_preview=dependency_files_preview,
            dependent_file_count=context.dependent_file_count,
            dependent_files_preview=dependent_files_preview,
            render_child_count=context.render_child_count,
            render_children_preview=render_children_preview,
            render_parent_count=context.render_parent_count,
            render_parents_preview=render_parents_preview,
            invariant_finding_count=context.invariant_finding_count,
            invariant_findings_preview=invariant_findings_preview,
            local_flow_edge_count=context.local_flow_edge_count,
            local_flow_edges_preview=local_flow_edges_preview,
            implementation_location_count=context.implementation_location_count,
            implementation_locations_preview=implementation_locations_preview,
            related_tests=related_tests,
            structured_artifact=structured_artifact_view,
            provenance=self._merge_view_provenance(
                owner.file.provenance,
                *(item.provenance for item in reference_sites_preview),
                *(item.provenance for item in dependency_files_preview),
                *(item.provenance for item in dependent_files_preview),
                *(item.provenance for item in render_children_preview),
                *(item.provenance for item in render_parents_preview),
                *(item.provenance for item in invariant_findings_preview),
                *(item.provenance for item in local_flow_edges_preview),
                *(item.provenance for item in implementation_locations_preview),
                *(item.provenance for item in related_tests),
                structured_artifact_view.provenance if structured_artifact_view is not None else tuple(),
            ),
        )

    @staticmethod
    def _validate_detail_level(detail_level: str) -> str:
        normalized = detail_level.strip().lower()
        if normalized not in {"compact", "standard", "full"}:
            raise McpValidationError("detail_level must be one of: compact, standard, full")
        return normalized

    @staticmethod
    def _detail_preview_limit(detail_level: str, requested_limit: int) -> int:
        if detail_level == "compact":
            return min(requested_limit, 3)
        if detail_level == "standard":
            return min(requested_limit, 10)
        return requested_limit

    @staticmethod
    def _compact_invariant_findings(invariant_findings):
        return tuple(item for item in invariant_findings if item.producer_site_count > 0)

    @staticmethod
    def _shape_structured_artifact_view(artifact_view, *, detail_level: str):
        if artifact_view.markdown is not None:
            limit = 3 if detail_level == "compact" else 10 if detail_level == "standard" else None
            if limit is not None:
                return artifact_view.model_copy(
                    update={
                        "markdown": artifact_view.markdown.model_copy(
                            update={
                                "sections": artifact_view.markdown.sections[:limit],
                                "code_blocks": artifact_view.markdown.code_blocks[:limit],
                                "links": artifact_view.markdown.links[:limit],
                                "checklist_items": artifact_view.markdown.checklist_items[:limit],
                            }
                        )
                    }
                )
        if artifact_view.openapi is not None:
            limit = 3 if detail_level == "compact" else 10 if detail_level == "standard" else None
            if limit is not None:
                return artifact_view.model_copy(
                    update={
                        "openapi": artifact_view.openapi.model_copy(
                            update={
                                "operations": artifact_view.openapi.operations[:limit],
                                "schemas": artifact_view.openapi.schemas[:limit],
                                "tags": artifact_view.openapi.tags[:limit],
                            }
                        )
                    }
                )
        return artifact_view

    def _compact_file_understanding_view(
        self,
        targets: tuple[FileUnderstandingTargetView, ...],
    ) -> FileUnderstandingCompactView:
        aggregate_reference_site_count, aggregate_reference_sites_preview = self._aggregate_ranked_views(
            tuple(target.reference_sites_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=3,
        )
        aggregate_dependency_file_count, aggregate_dependency_files_preview = self._aggregate_ranked_views(
            tuple(target.dependency_files_preview for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=3,
        )
        aggregate_dependent_file_count, aggregate_dependent_files_preview = self._aggregate_ranked_views(
            tuple(target.dependent_files_preview for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=3,
        )
        aggregate_render_child_count, aggregate_render_children_preview = self._aggregate_ranked_views(
            tuple(target.render_children_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=3,
        )
        aggregate_render_parent_count, aggregate_render_parents_preview = self._aggregate_ranked_views(
            tuple(target.render_parents_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=3,
        )
        aggregate_invariant_finding_count, aggregate_invariant_findings_preview = self._aggregate_ranked_views(
            tuple(self._compact_invariant_findings(target.invariant_findings_preview) for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
            rank_key=self._invariant_rank_key,
            limit=3,
        )
        aggregate_local_flow_edge_count, aggregate_local_flow_edges_preview = self._aggregate_ranked_views(
            tuple(target.local_flow_edges_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
            rank_key=self._static_flow_rank_key,
            limit=3,
        )
        _, aggregate_related_tests = self._aggregate_ranked_views(
            tuple(target.related_tests for target in targets),
            key=lambda item: item.id,
            rank_key=self._related_test_rank_key,
            limit=3,
        )
        compact_targets = tuple(
            FileUnderstandingCompactTargetView(
                detail_level="compact",
                repository_rel_path=target.repository_rel_path,
                file_owner=target.file_owner,
                reference_site_count=target.reference_site_count,
                reference_sites_preview=target.reference_sites_preview[:3],
                dependency_file_count=target.dependency_file_count,
                dependency_files_preview=target.dependency_files_preview[:3],
                dependent_file_count=target.dependent_file_count,
                dependent_files_preview=target.dependent_files_preview[:3],
                render_child_count=target.render_child_count,
                render_children_preview=target.render_children_preview[:3],
                render_parent_count=target.render_parent_count,
                render_parents_preview=target.render_parents_preview[:3],
                invariant_finding_count=len(self._compact_invariant_findings(target.invariant_findings_preview)),
                invariant_findings_preview=self._compact_invariant_findings(target.invariant_findings_preview)[:3],
                local_flow_edge_count=target.local_flow_edge_count,
                local_flow_edges_preview=target.local_flow_edges_preview[:3],
                related_test_count=len(target.related_tests),
                related_tests=target.related_tests[:3],
                structured_artifact=target.structured_artifact,
            )
            for target in targets
        )
        return FileUnderstandingCompactView(
            detail_level="compact",
            target_count=len(compact_targets),
            targets=compact_targets,
            owner_ids=tuple(sorted({item.file_owner.owner.id for item in compact_targets})),
            aggregate_reference_site_count=aggregate_reference_site_count,
            aggregate_reference_sites_preview=aggregate_reference_sites_preview,
            aggregate_dependency_file_count=aggregate_dependency_file_count,
            aggregate_dependency_files_preview=aggregate_dependency_files_preview,
            aggregate_dependent_file_count=aggregate_dependent_file_count,
            aggregate_dependent_files_preview=aggregate_dependent_files_preview,
            aggregate_render_child_count=aggregate_render_child_count,
            aggregate_render_children_preview=aggregate_render_children_preview,
            aggregate_render_parent_count=aggregate_render_parent_count,
            aggregate_render_parents_preview=aggregate_render_parents_preview,
            aggregate_invariant_finding_count=aggregate_invariant_finding_count,
            aggregate_invariant_findings_preview=aggregate_invariant_findings_preview,
            aggregate_local_flow_edge_count=aggregate_local_flow_edge_count,
            aggregate_local_flow_edges_preview=aggregate_local_flow_edges_preview,
            aggregate_related_tests=aggregate_related_tests,
            suggested_follow_ups=(
                tuple()
                if compact_targets and all(target.structured_artifact is not None for target in compact_targets)
                else (
                    "what_changes_if_i_edit_this",
                    "what_should_i_run",
                    "can_i_do_this",
                )
            ),
        )

    def _standard_file_understanding_view(
        self,
        targets: tuple[FileUnderstandingTargetView, ...],
    ) -> FileUnderstandingStandardView:
        aggregate_reference_site_count, aggregate_reference_sites_preview = self._aggregate_ranked_views(
            tuple(target.reference_sites_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=10,
        )
        aggregate_dependency_file_count, aggregate_dependency_files_preview = self._aggregate_ranked_views(
            tuple(target.dependency_files_preview for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=10,
        )
        aggregate_dependent_file_count, aggregate_dependent_files_preview = self._aggregate_ranked_views(
            tuple(target.dependent_files_preview for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=10,
        )
        aggregate_render_child_count, aggregate_render_children_preview = self._aggregate_ranked_views(
            tuple(target.render_children_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=10,
        )
        aggregate_render_parent_count, aggregate_render_parents_preview = self._aggregate_ranked_views(
            tuple(target.render_parents_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=10,
        )
        aggregate_invariant_finding_count, aggregate_invariant_findings_preview = self._aggregate_ranked_views(
            tuple(target.invariant_findings_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
            rank_key=self._invariant_rank_key,
            limit=10,
        )
        aggregate_local_flow_edge_count, aggregate_local_flow_edges_preview = self._aggregate_ranked_views(
            tuple(target.local_flow_edges_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
            rank_key=self._static_flow_rank_key,
            limit=10,
        )
        aggregate_implementation_location_count, aggregate_implementation_locations_preview = self._aggregate_ranked_views(
            tuple(target.implementation_locations_preview for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=10,
        )
        _, aggregate_related_tests = self._aggregate_ranked_views(
            tuple(target.related_tests for target in targets),
            key=lambda item: item.id,
            rank_key=self._related_test_rank_key,
            limit=10,
        )
        standard_targets = tuple(
            FileUnderstandingStandardTargetView(
                detail_level="standard",
                repository_rel_path=target.repository_rel_path,
                file_owner=target.file_owner,
                reference_site_count=target.reference_site_count,
                reference_sites_preview=target.reference_sites_preview[:10],
                dependency_file_count=target.dependency_file_count,
                dependency_files_preview=target.dependency_files_preview[:10],
                dependent_file_count=target.dependent_file_count,
                dependent_files_preview=target.dependent_files_preview[:10],
                render_child_count=target.render_child_count,
                render_children_preview=target.render_children_preview[:10],
                render_parent_count=target.render_parent_count,
                render_parents_preview=target.render_parents_preview[:10],
                invariant_finding_count=target.invariant_finding_count,
                invariant_findings_preview=target.invariant_findings_preview[:10],
                local_flow_edge_count=target.local_flow_edge_count,
                local_flow_edges_preview=target.local_flow_edges_preview[:10],
                implementation_location_count=target.implementation_location_count,
                implementation_locations_preview=target.implementation_locations_preview[:10],
                related_test_count=len(target.related_tests),
                related_tests=target.related_tests[:10],
                structured_artifact=target.structured_artifact,
            )
            for target in targets
        )
        return FileUnderstandingStandardView(
            detail_level="standard",
            target_count=len(standard_targets),
            targets=standard_targets,
            owner_ids=tuple(sorted({item.file_owner.owner.id for item in standard_targets})),
            aggregate_reference_site_count=aggregate_reference_site_count,
            aggregate_reference_sites_preview=aggregate_reference_sites_preview,
            aggregate_dependency_file_count=aggregate_dependency_file_count,
            aggregate_dependency_files_preview=aggregate_dependency_files_preview,
            aggregate_dependent_file_count=aggregate_dependent_file_count,
            aggregate_dependent_files_preview=aggregate_dependent_files_preview,
            aggregate_render_child_count=aggregate_render_child_count,
            aggregate_render_children_preview=aggregate_render_children_preview,
            aggregate_render_parent_count=aggregate_render_parent_count,
            aggregate_render_parents_preview=aggregate_render_parents_preview,
            aggregate_invariant_finding_count=aggregate_invariant_finding_count,
            aggregate_invariant_findings_preview=aggregate_invariant_findings_preview,
            aggregate_local_flow_edge_count=aggregate_local_flow_edge_count,
            aggregate_local_flow_edges_preview=aggregate_local_flow_edges_preview,
            aggregate_implementation_location_count=aggregate_implementation_location_count,
            aggregate_implementation_locations_preview=aggregate_implementation_locations_preview,
            aggregate_related_tests=aggregate_related_tests,
            suggested_follow_ups=(
                tuple()
                if standard_targets and all(target.structured_artifact is not None for target in standard_targets)
                else (
                    "what_changes_if_i_edit_this",
                    "what_should_i_run",
                    "can_i_do_this",
                )
            ),
        )

    def _compact_change_impact_view(
        self,
        targets: tuple[BatchChangeImpactTargetView, ...],
    ) -> BatchChangeImpactCompactView:
        _, reference_sites = self._aggregate_ranked_views(
            tuple(target.impact.reference_locations for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=3,
        )
        _, dependent_files = self._aggregate_ranked_views(
            tuple(target.impact.dependent_files for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=3,
        )
        _, render_children = self._aggregate_ranked_views(
            tuple(target.impact.render_children for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=3,
        )
        _, render_parents = self._aggregate_ranked_views(
            tuple(target.impact.render_parents for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=3,
        )
        _, invariant_findings = self._aggregate_ranked_views(
            tuple(self._compact_invariant_findings(target.impact.invariant_findings) for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
            rank_key=self._invariant_rank_key,
            limit=3,
        )
        _, local_flow_edges = self._aggregate_ranked_views(
            tuple(target.impact.local_flow_edges for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
            rank_key=self._static_flow_rank_key,
            limit=3,
        )
        _, dependent_components = self._aggregate_ranked_views(
            tuple(target.impact.dependent_components for target in targets),
            key=lambda item: item.id,
            rank_key=self._component_rank_key,
            limit=3,
        )
        _, related_tests = self._aggregate_ranked_views(
            tuple(target.impact.related_tests for target in targets),
            key=lambda item: item.test.id,
            rank_key=self._test_impact_rank_key,
            limit=3,
        )
        _, related_runners = self._aggregate_ranked_views(
            tuple(target.impact.related_runners for target in targets),
            key=lambda item: item.runner.id,
            rank_key=self._runner_impact_rank_key,
            limit=3,
        )
        _, quality_gates = self._aggregate_ranked_views(
            tuple(target.impact.quality_gates for target in targets),
            key=lambda item: (item.provider_id, item.reason, item.applies),
            rank_key=self._quality_gate_rank_key,
            limit=3,
        )
        compact_targets = tuple(
            BatchChangeImpactCompactTargetView(
                detail_level="compact",
                repository_rel_path=target.repository_rel_path,
                owner=target.impact.owner,
                primary_component=target.impact.primary_component,
                reference_sites=target.impact.reference_locations[:3],
                dependent_files=target.impact.dependent_files[:3],
                render_children=target.impact.render_children[:3],
                render_parents=target.impact.render_parents[:3],
                invariant_findings=self._compact_invariant_findings(target.impact.invariant_findings)[:3],
                local_flow_edges=target.impact.local_flow_edges[:3],
                dependent_components=target.impact.dependent_components[:3],
                related_tests=target.impact.related_tests[:3],
                related_runners=target.impact.related_runners[:3],
                quality_gates=target.impact.quality_gates[:3],
            )
            for target in targets
        )
        return BatchChangeImpactCompactView(
            detail_level="compact",
            target_count=len(compact_targets),
            targets=compact_targets,
            owner_ids=tuple(sorted({item.owner.id for item in compact_targets})),
            reference_sites=reference_sites,
            dependent_files=dependent_files,
            render_children=render_children,
            render_parents=render_parents,
            invariant_findings=invariant_findings,
            local_flow_edges=local_flow_edges,
            dependent_components=dependent_components,
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
        )

    def _standard_change_impact_view(
        self,
        targets: tuple[BatchChangeImpactTargetView, ...],
    ) -> BatchChangeImpactStandardView:
        _, reference_sites = self._aggregate_ranked_views(
            tuple(target.impact.reference_locations for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=10,
        )
        _, dependent_files = self._aggregate_ranked_views(
            tuple(target.impact.dependent_files for target in targets),
            key=lambda item: item.path,
            rank_key=self._file_relationship_rank_key,
            limit=10,
        )
        _, render_children = self._aggregate_ranked_views(
            tuple(target.impact.render_children for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=10,
        )
        _, render_parents = self._aggregate_ranked_views(
            tuple(target.impact.render_parents for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.prop_names, item.has_spread_props),
            rank_key=self._render_edge_rank_key,
            limit=10,
        )
        _, invariant_findings = self._aggregate_ranked_views(
            tuple(target.impact.invariant_findings for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.field_name, item.subject_label),
            rank_key=self._invariant_rank_key,
            limit=10,
        )
        _, local_flow_edges = self._aggregate_ranked_views(
            tuple(target.impact.local_flow_edges for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.edge_kind, item.source_label, item.target_label),
            rank_key=self._static_flow_rank_key,
            limit=10,
        )
        _, implementation_locations = self._aggregate_ranked_views(
            tuple(target.impact.implementation_locations for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=10,
        )
        _, implementation_components = self._aggregate_ranked_views(
            tuple(target.impact.implementation_components for target in targets),
            key=lambda item: item.id,
            rank_key=self._component_rank_key,
            limit=10,
        )
        _, dependent_components = self._aggregate_ranked_views(
            tuple(target.impact.dependent_components for target in targets),
            key=lambda item: item.id,
            rank_key=self._component_rank_key,
            limit=10,
        )
        _, reference_locations = self._aggregate_ranked_views(
            tuple(target.impact.reference_locations for target in targets),
            key=lambda item: (item.path, item.line_start, item.column_start, item.line_end, item.column_end, item.symbol_id),
            rank_key=self._location_rank_key,
            limit=10,
        )
        _, related_tests = self._aggregate_ranked_views(
            tuple(target.impact.related_tests for target in targets),
            key=lambda item: item.test.id,
            rank_key=self._test_impact_rank_key,
            limit=10,
        )
        _, related_runners = self._aggregate_ranked_views(
            tuple(target.impact.related_runners for target in targets),
            key=lambda item: item.runner.id,
            rank_key=self._runner_impact_rank_key,
            limit=10,
        )
        _, quality_gates = self._aggregate_ranked_views(
            tuple(target.impact.quality_gates for target in targets),
            key=lambda item: (item.provider_id, item.reason, item.applies),
            rank_key=self._quality_gate_rank_key,
            limit=10,
        )
        standard_targets = tuple(
            BatchChangeImpactStandardTargetView(
                detail_level="standard",
                repository_rel_path=target.repository_rel_path,
                owner=target.impact.owner,
                primary_component=target.impact.primary_component,
                reference_sites=target.impact.reference_locations[:10],
                dependency_files=target.impact.dependency_files[:10],
                dependent_files=target.impact.dependent_files[:10],
                render_children=target.impact.render_children[:10],
                render_parents=target.impact.render_parents[:10],
                invariant_findings=target.impact.invariant_findings[:10],
                local_flow_edges=target.impact.local_flow_edges[:10],
                implementation_locations=target.impact.implementation_locations[:10],
                implementation_components=target.impact.implementation_components[:10],
                dependent_components=target.impact.dependent_components[:10],
                reference_locations=target.impact.reference_locations[:10],
                related_tests=target.impact.related_tests[:10],
                related_runners=target.impact.related_runners[:10],
                quality_gates=target.impact.quality_gates[:10],
            )
            for target in targets
        )
        return BatchChangeImpactStandardView(
            detail_level="standard",
            target_count=len(standard_targets),
            targets=standard_targets,
            owner_ids=tuple(sorted({item.owner.id for item in standard_targets})),
            reference_sites=reference_sites,
            dependent_files=dependent_files,
            render_children=render_children,
            render_parents=render_parents,
            invariant_findings=invariant_findings,
            local_flow_edges=local_flow_edges,
            implementation_locations=implementation_locations,
            implementation_components=implementation_components,
            dependent_components=dependent_components,
            reference_locations=reference_locations,
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
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

    @staticmethod
    def _aggregate_ranked_views(
        groups: tuple[tuple[T, ...], ...],
        *,
        key: Callable[[T], object],
        rank_key: Callable[[T], tuple[object, ...]],
        limit: int | None = None,
    ) -> tuple[int, tuple[T, ...]]:
        first_items: dict[object, T] = {}
        support_counts: dict[object, int] = {}
        first_positions: dict[object, tuple[int, int]] = {}
        for group_index, group in enumerate(groups):
            seen_in_group: set[object] = set()
            for item_index, item in enumerate(group):
                item_key = key(item)
                if item_key in seen_in_group:
                    continue
                seen_in_group.add(item_key)
                support_counts[item_key] = support_counts.get(item_key, 0) + 1
                if item_key in first_items:
                    continue
                first_items[item_key] = item
                first_positions[item_key] = (group_index, item_index)

        ordered = sorted(
            first_items.items(),
            key=lambda entry: (
                -support_counts[entry[0]],
                first_positions[entry[0]][0],
                first_positions[entry[0]][1],
                rank_key(entry[1]),
            ),
        )
        preview = tuple(item for _, item in ordered[:limit] if limit is not None) if limit is not None else tuple(
            item for _, item in ordered
        )
        return len(first_items), preview

    @staticmethod
    def _location_rank_key(item: LocationView) -> tuple[object, ...]:
        return (
            item.path,
            item.line_start,
            item.column_start,
            item.line_end or 0,
            item.column_end or 0,
            item.symbol_id or "",
        )

    @staticmethod
    def _file_relationship_rank_key(item) -> tuple[object, ...]:
        return (item.path,)

    @staticmethod
    def _render_edge_rank_key(item) -> tuple[object, ...]:
        return (
            item.path,
            item.line_start,
            item.column_start,
            item.has_spread_props,
            item.prop_names,
        )

    @staticmethod
    def _invariant_rank_key(item) -> tuple[object, ...]:
        return (
            -item.producer_site_count,
            item.path,
            item.line_start,
            item.column_start,
            item.field_name,
            item.subject_label,
        )

    @staticmethod
    def _static_flow_rank_key(item) -> tuple[object, ...]:
        return (
            item.path,
            item.line_start,
            item.column_start,
            item.edge_kind,
            item.source_label,
            item.target_label,
        )

    @staticmethod
    def _related_test_rank_key(item: RelatedTestView) -> tuple[object, ...]:
        relation_rank = 2
        if item.matched_path is not None:
            relation_rank = 0
        elif item.matched_owner_id is not None:
            relation_rank = 1
        return (relation_rank, item.id)

    @staticmethod
    def _test_impact_rank_key(item) -> tuple[object, ...]:
        relation_rank = 2
        if item.test.matched_path is not None:
            relation_rank = 0
        elif item.test.matched_owner_id is not None:
            relation_rank = 1
        return (relation_rank, item.test.id)

    @staticmethod
    def _component_rank_key(item) -> tuple[object, ...]:
        return (item.id,)

    @staticmethod
    def _runner_impact_rank_key(item) -> tuple[object, ...]:
        return (item.runner.id,)

    @staticmethod
    def _quality_gate_rank_key(item) -> tuple[object, ...]:
        return (
            not item.applies,
            item.provider_id,
            item.reason,
        )

    @staticmethod
    def _narrow_batch_minimum_verified_tests(
        *,
        tests: tuple[MinimumVerifiedTestTargetView, ...],
        build_targets: tuple[MinimumVerifiedBuildTargetView, ...],
        excluded_items: tuple[ExcludedMinimumVerifiedItemView, ...],
    ) -> tuple[tuple[MinimumVerifiedTestTargetView, ...], tuple[ExcludedMinimumVerifiedItemView, ...]]:
        build_target_ids = {item.action_id for item in build_targets}
        replacement_exclusions = {
            item.item_id: item
            for item in excluded_items
            if item.reason_code == "dependent_test_replaced_by_narrower_build"
            and item.replaced_by_ids
            and set(item.replaced_by_ids).issubset(build_target_ids)
        }
        if not replacement_exclusions:
            return tests, excluded_items
        narrowed_tests = tuple(item for item in tests if item.test_id not in replacement_exclusions)
        return narrowed_tests, excluded_items

    @staticmethod
    def _filter_batch_minimum_verified_exclusions(
        excluded_items: tuple[ExcludedMinimumVerifiedItemView, ...],
    ) -> tuple[ExcludedMinimumVerifiedItemView, ...]:
        allowed_reason_codes = {
            "dependent_test_replaced_by_narrower_build",
            "repository_build_replaced_by_narrower_build",
            "no_deterministic_test_targets_available",
            "no_deterministic_validation_surfaces_for_provider_owned_artifact",
        }
        return tuple(item for item in excluded_items if item.reason_code in allowed_reason_codes)

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
