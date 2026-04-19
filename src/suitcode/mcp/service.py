from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
import time
from typing import Callable, TypeVar

from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.core.code.evidence_tier import CodeEvidenceTier
from suitcode.core.change_models import ChangeTarget
from suitcode.core.repository import Repository
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.validation import validate_preview_limit
from suitcode.core.validation import validate_change_preview_limit
from suitcode.mcp.errors import McpNotFoundError, McpRetryableError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.file_target_errors import explain_file_target_error
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
    CompactRiskView,
    CompactSurfaceBoundaryView,
    DependencyRefView,
    ExcludedMinimumVerifiedItemView,
    ExternalPackageView,
    ArtifactSurfaceSummaryView,
    BatchProofGapView,
    FileContextView,
    FrontendProofSummaryView,
    FileOwnerView,
    FileUnderstandingTargetView,
    FileUnderstandingView,
    FileUnderstandingCompactTargetView,
    FileUnderstandingCompactView,
    FileUnderstandingStandardTargetView,
    FileUnderstandingStandardView,
    IncompleteBatchTargetView,
    FileView,
    ImpactSummaryView,
    HotEntrypointView,
    InefficientToolCallView,
    ListResult,
    LocationView,
    MinimumVerifiedBuildTargetView,
    MinimumVerifiedCompactItemView,
    MinimumVerifiedCompactSummaryView,
    MinimumVerifiedTestTargetView,
    OpenWorkspaceResult,
    PackageManagerView,
    ProofGapItemView,
    ProofGapTargetView,
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
from suitcode.mcp.state import ReadOnlyRepositoryRegistry, WorkspaceRegistry
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.npm.tool_runner import TypeScriptToolTimeoutError
from suitcode.runtime.client import ProjectCoordinatorClient
from suitcode.runtime.errors import CoordinatorRuntimeNotReadyError, SemanticQueryTimeoutError

T = TypeVar("T")


class SuitMcpService:
    _BATCH_COMPACT_MAX_WORKERS = 4
    _BATCH_COMPACT_TARGET_TIMEOUT_SECONDS = 120.0
    _STANDARD_MAX_TARGETS = 3
    _FULL_MAX_TARGETS = 1
    _COMPACT_SINGLE_TARGET_STRUCTURAL_LINE_THRESHOLD = 400
    _COMPACT_SINGLE_TARGET_STRUCTURAL_BYTE_THRESHOLD = 48 * 1024
    _SEMANTIC_RUNTIME_MAX_ATTEMPTS = 3
    _SEMANTIC_RUNTIME_MAX_TOTAL_RETRY_SLEEP_SECONDS = 30.0
    _SEMANTIC_RUNTIME_MAX_TOTAL_WALL_CLOCK_SECONDS = 45.0

    def __init__(
        self,
        registry: WorkspaceRegistry | None = None,
        pagination: PaginationPolicy | None = None,
        read_only_registry: ReadOnlyRepositoryRegistry | None = None,
    ) -> None:
        self._registry = registry or WorkspaceRegistry()
        self._read_only_registry = read_only_registry or ReadOnlyRepositoryRegistry()
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

        return self._with_read_only_repository(repository_path, _callback, tool_name="repository_summary_by_path")

    def understand_repository(
        self,
        repository_path: str,
        preview_limit: int = 10,
    ) -> RepositoryUnderstandingView:
        validate_preview_limit(preview_limit, "preview_limit", max_value=50, error_cls=McpValidationError)

        def _callback(repository: Repository) -> RepositoryUnderstandingView:
            self._wait_for_repository_warmup(repository)
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

        return self._with_read_only_repository(repository_path, _callback, tool_name="understand_repository")

    def _wait_for_repository_warmup(self, repository: Repository) -> None:
        ProjectCoordinatorClient(repository.root).wait_for_project_warmup(
            timeout_seconds=None,
        )

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
            target_count = len(normalized_paths)
            self._validate_detail_scope(
                tool_name="understand_file",
                detail_level=validated_detail_level,
                target_count=target_count,
            )
            degrade_compact_single_target = self._should_degrade_compact_single_target(
                repository,
                normalized_paths,
                detail_level=validated_detail_level,
            )
            enable_deep_symbol_navigation = (
                False
                if degrade_compact_single_target
                else self._should_enable_deep_symbol_navigation(
                    validated_detail_level,
                    target_count,
                )
            )
            evidence_tier = (
                CodeEvidenceTier.STRUCTURAL
                if degrade_compact_single_target
                else self._code_evidence_tier(validated_detail_level, target_count)
            )
            include_file_wide_references = enable_deep_symbol_navigation
            targets, incomplete_targets = self._collect_understand_file_targets(
                repository=repository,
                repository_rel_paths=normalized_paths,
                related_test_limit=self._detail_preview_limit(validated_detail_level, related_test_limit),
                detail_level=validated_detail_level,
                include_reference_sites=include_file_wide_references,
                include_implementation_locations=enable_deep_symbol_navigation,
                enable_implementation_flow=enable_deep_symbol_navigation,
                enable_hot_entrypoints=enable_deep_symbol_navigation,
                reference_site_limit=(
                    None
                    if enable_deep_symbol_navigation
                    else self._detail_preview_limit(validated_detail_level, 20)
                ),
                evidence_tier=evidence_tier,
            )
            if validated_detail_level == "compact":
                return self._compact_file_understanding_view(
                    repository,
                    targets,
                    target_count=target_count,
                    incomplete_targets=incomplete_targets,
                )
            if validated_detail_level == "standard":
                return self._standard_file_understanding_view(
                    targets,
                    target_count=target_count,
                    incomplete_targets=incomplete_targets,
                )
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
                target_count=target_count,
                completed_target_count=len(targets),
                targets=targets,
                incomplete_targets=incomplete_targets,
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

        return self._with_read_only_repository(repository_path, _callback, tool_name="understand_file")

    def get_file_owner_by_path(self, repository_path: str, repository_rel_path: str) -> FileOwnerView:
        def _callback(repository: Repository) -> FileOwnerView:
            try:
                return self._ownership_presenter.file_owner_view(repository.get_file_owner(repository_rel_path))
            except ValueError as exc:
                raise McpNotFoundError(
                    explain_file_target_error(
                        repository,
                        repository_rel_path,
                        str(exc),
                        tool_name="get_file_owner_by_path",
                    )
                ) from exc

        return self._with_read_only_repository(repository_path, _callback, tool_name="get_file_owner_by_path")

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
                message = str(exc)
                if repository_rel_path is not None:
                    message = explain_file_target_error(
                        repository,
                        repository_rel_path,
                        message,
                        tool_name="get_related_tests_by_path",
                    )
                raise McpValidationError(message) from exc

        return self._with_read_only_repository(repository_path, _callback, tool_name="get_related_tests_by_path")

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
            target_count = len(normalized_paths)
            self._validate_detail_scope(
                tool_name="what_changes_if_i_edit_this",
                detail_level=validated_detail_level,
                target_count=target_count,
            )
            degrade_compact_single_target = self._should_degrade_compact_single_target(
                repository,
                normalized_paths,
                detail_level=validated_detail_level,
            )
            enable_deep_symbol_navigation = (
                False
                if degrade_compact_single_target
                else self._should_enable_deep_symbol_navigation(
                    validated_detail_level,
                    target_count,
                )
            )
            evidence_tier = (
                CodeEvidenceTier.STRUCTURAL
                if degrade_compact_single_target
                else self._code_evidence_tier(validated_detail_level, target_count)
            )
            include_file_wide_references = enable_deep_symbol_navigation
            frozen_targets, incomplete_targets = self._collect_change_impact_targets(
                repository=repository,
                repository_rel_paths=normalized_paths,
                detail_level=validated_detail_level,
                reference_preview_limit=self._detail_preview_limit(validated_detail_level, reference_preview_limit),
                dependent_preview_limit=self._detail_preview_limit(validated_detail_level, dependent_preview_limit),
                test_preview_limit=self._detail_preview_limit(validated_detail_level, test_preview_limit),
                runner_preview_limit=self._detail_preview_limit(validated_detail_level, runner_preview_limit),
                include_reference_locations=include_file_wide_references,
                include_implementation_locations=enable_deep_symbol_navigation,
                evidence_tier=evidence_tier,
                enable_deep_symbol_navigation=enable_deep_symbol_navigation,
            )
            if validated_detail_level == "compact":
                return self._compact_change_impact_view(
                    repository,
                    frozen_targets,
                    target_count=target_count,
                    incomplete_targets=incomplete_targets,
                )
            if validated_detail_level == "standard":
                return self._standard_change_impact_view(
                    frozen_targets,
                    target_count=target_count,
                    incomplete_targets=incomplete_targets,
                )
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
                target_count=target_count,
                completed_target_count=len(frozen_targets),
                targets=frozen_targets,
                incomplete_targets=incomplete_targets,
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

        return self._with_read_only_repository(repository_path, _callback, tool_name="what_changes_if_i_edit_this")

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
                message = str(exc)
                if repository_rel_path is not None:
                    message = explain_file_target_error(
                        repository,
                        repository_rel_path,
                        message,
                        tool_name="get_minimum_verified_change_set_by_path",
                    )
                raise McpValidationError(message) from exc

        return self._with_read_only_repository(repository_path, _callback, tool_name="get_minimum_verified_change_set_by_path")

    def what_should_i_run(
        self,
        repository_path: str,
        repository_rel_paths: tuple[str, ...],
    ) -> BatchMinimumVerifiedChangeSetView:
        def _callback(repository: Repository) -> BatchMinimumVerifiedChangeSetView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets: list[BatchMinimumVerifiedChangeSetTargetView] = []
            for repository_rel_path in normalized_paths:
                targets.append(
                    self._minimum_verified_batch_target_view(
                        repository,
                        repository_rel_path,
                        tool_name="what_should_i_run",
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
            compact_summary = self._batch_minimum_verified_compact_summary(
                targets=frozen_targets,
                tests=tests,
                build_targets=build_targets,
                runner_actions=runner_actions,
                quality_validation_operations=quality_validation_operations,
                quality_hygiene_operations=quality_hygiene_operations,
                excluded_items=excluded_items,
            )
            return BatchMinimumVerifiedChangeSetView(
                compact_summary=compact_summary,
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

        return self._with_read_only_repository(repository_path, _callback, tool_name="what_should_i_run")

    def what_is_not_proven(
        self,
        repository_path: str,
        repository_rel_paths: tuple[str, ...],
    ) -> BatchProofGapView:
        def _callback(repository: Repository) -> BatchProofGapView:
            normalized_paths = self._validate_repository_rel_paths(repository_rel_paths, field_name="repository_rel_paths")
            targets = tuple(
                self._proof_gap_target_view(repository, repository_rel_path)
                for repository_rel_path in normalized_paths
            )
            targets_with_gaps = tuple(target for target in targets if target.gap_items)
            shared_gap_codes = tuple(
                sorted(
                    set.intersection(*(set(item.gap_code for item in target.gap_items) for target in targets_with_gaps))
                )
            ) if len(targets_with_gaps) > 1 else (
                tuple(sorted({item.gap_code for item in targets_with_gaps[0].gap_items}))
                if targets_with_gaps
                else tuple()
            )
            nearby_validation_surfaces = self._dedupe_views(
                tuple(item for target in targets for item in target.nearest_validation_artifacts),
                key=lambda item: (item.item_kind, item.item_id),
            )
            ranked_targets = tuple(
                item.repository_rel_path
                for item in sorted(
                    targets_with_gaps,
                    key=lambda target: (
                        -self._proof_gap_priority(target.gap_items),
                        target.repository_rel_path,
                    ),
                )[:3]
            )
            return BatchProofGapView(
                target_count=len(targets),
                targets=targets,
                highest_priority_targets=ranked_targets,
                shared_gap_codes=shared_gap_codes,
                nearby_validation_surfaces=nearby_validation_surfaces,
            )

        return self._with_read_only_repository(repository_path, _callback, tool_name="what_is_not_proven")

    def _minimum_verified_batch_target_view(
        self,
        repository: Repository,
        repository_rel_path: str,
        *,
        tool_name: str,
    ) -> BatchMinimumVerifiedChangeSetTargetView:
        try:
            change_set = repository.get_minimum_verified_change_set(ChangeTarget(repository_rel_path=repository_rel_path))
        except ValueError as exc:
            raise McpValidationError(
                explain_file_target_error(
                    repository,
                    repository_rel_path,
                    str(exc),
                    tool_name=tool_name,
                )
            ) from exc
        return BatchMinimumVerifiedChangeSetTargetView(
            repository_rel_path=repository_rel_path,
            change_set=self._change_impact_presenter.minimum_verified_change_set_view(change_set),
        )

    def _batch_minimum_verified_compact_summary(
        self,
        *,
        targets: tuple[BatchMinimumVerifiedChangeSetTargetView, ...],
        tests: tuple[MinimumVerifiedTestTargetView, ...],
        build_targets: tuple[MinimumVerifiedBuildTargetView, ...],
        runner_actions,
        quality_validation_operations,
        quality_hygiene_operations,
        excluded_items: tuple[ExcludedMinimumVerifiedItemView, ...],
    ) -> MinimumVerifiedCompactSummaryView:
        base = self._change_impact_presenter.minimum_verified_compact_summary_view(
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
            excluded_items=excluded_items,
        )
        reserved: list[MinimumVerifiedCompactItemView] = []
        seen_ids: set[tuple[str, str]] = set()
        for target in targets:
            for item in target.change_set.compact_summary.required_validation:
                key = (item.item_kind, item.item_id)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                reserved.append(item)
                break
        ordered_required = tuple(
            [
                *reserved,
                *(
                    item
                    for item in base.required_validation
                    if (item.item_kind, item.item_id) not in seen_ids
                ),
            ]
        )
        return MinimumVerifiedCompactSummaryView(
            required_validation_count=base.required_validation_count,
            required_validation=ordered_required,
            optional_hygiene_count=base.optional_hygiene_count,
            optional_hygiene=base.optional_hygiene,
            exclusion_count=base.exclusion_count,
            exclusions=base.exclusions,
        )

    def _proof_gap_target_view(
        self,
        repository: Repository,
        repository_rel_path: str,
    ) -> ProofGapTargetView:
        minimum = self._minimum_verified_batch_target_view(
            repository,
            repository_rel_path,
            tool_name="what_is_not_proven",
        )
        change_set = minimum.change_set
        validation_surfaces = change_set.compact_summary.required_validation
        nearest_validation_artifacts = validation_surfaces[:3]
        validation_is_build_only = bool(validation_surfaces) and all(
            item.item_kind == "build_target" for item in validation_surfaces
        )
        has_focused_test_surface = bool(change_set.tests)
        has_runner_surface = bool(change_set.runner_actions)
        artifact_surface_summary = self._artifact_surface_summary_view(repository, repository_rel_path)
        gap_items: list[ProofGapItemView] = []
        if not validation_surfaces:
            gap_items.append(
                ProofGapItemView(
                    gap_code="no_deterministic_validation_surface",
                    summary="No deterministic validation surface was identified for this target.",
                )
            )
        if artifact_surface_summary is not None and not validation_surfaces:
            gap_items.append(
                ProofGapItemView(
                    gap_code="artifact_member_without_validation_surface",
                    summary="This artifact member has no deterministic validation surface beyond ownership.",
                )
            )
        if validation_is_build_only and self._is_frontend_npm_file_target(repository, repository_rel_path):
            gap_items.append(
                ProofGapItemView(
                    gap_code="build_only_frontend_surface",
                    summary="Frontend proof currently bottoms out at build-only validation.",
                )
            )
        if not has_focused_test_surface:
            gap_items.append(
                ProofGapItemView(
                    gap_code="no_focused_test_surface",
                    summary="No focused deterministic test surface was identified.",
                )
            )
        if any(item.reason_code == "no_narrower_direct_validation_surface_for_file_target" for item in change_set.excluded_items):
            gap_items.append(
                ProofGapItemView(
                    gap_code="only_broad_owner_level_validation",
                    summary="Only broader owner-level validation surfaces were found for this file target.",
                )
            )
        gap_items = list(
            self._dedupe_views(
                tuple(gap_items),
                key=lambda item: item.gap_code,
            )
        )
        return ProofGapTargetView(
            repository_rel_path=repository_rel_path,
            owner=change_set.owner,
            primary_component=change_set.primary_component,
            current_validation_surfaces=validation_surfaces,
            validation_is_build_only=validation_is_build_only,
            has_focused_test_surface=has_focused_test_surface,
            has_runner_surface=has_runner_surface,
            gap_items=tuple(gap_items),
            nearest_validation_artifacts=nearest_validation_artifacts,
            gap_summary=self._proof_gap_summary(
                repository_rel_path=repository_rel_path,
                validation_surfaces=validation_surfaces,
                gap_items=tuple(gap_items),
            ),
        )

    @staticmethod
    def _proof_gap_summary(
        *,
        repository_rel_path: str,
        validation_surfaces: tuple[MinimumVerifiedCompactItemView, ...],
        gap_items: tuple[ProofGapItemView, ...],
    ) -> tuple[str, ...]:
        statements = [
            (
                f"{len(validation_surfaces)} deterministic validation surfaces were found for `{repository_rel_path}`."
                if validation_surfaces
                else f"No deterministic validation surfaces were found for `{repository_rel_path}`."
            ),
            (
                f"Highest proof gap: {gap_items[0].summary}"
                if gap_items
                else "No deterministic proof gaps were detected from current repository evidence."
            ),
        ]
        if len(gap_items) > 1:
            statements.append(f"{len(gap_items)} distinct proof-gap codes were identified.")
        return tuple(statements[:3])

    @staticmethod
    def _proof_gap_priority(gap_items: tuple[ProofGapItemView, ...]) -> int:
        weights = {
            "no_deterministic_validation_surface": 5,
            "artifact_member_without_validation_surface": 4,
            "build_only_frontend_surface": 3,
            "no_focused_test_surface": 2,
            "only_broad_owner_level_validation": 1,
        }
        return sum(weights.get(item.gap_code, 0) for item in gap_items)

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
            try:
                target = ChangeTarget(repository_rel_path=repository_rel_path)
                truth_coverage = self._intelligence_presenter.truth_coverage_summary_view(
                    repository.get_change_truth_coverage(target)
                )
                owner = self._ownership_presenter.owner_view(repository.get_file_owner(repository_rel_path).owner)
                primary_component = None
                minimum_verified = None
                available_action_kinds: tuple[str, ...] = tuple()
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
                    raise McpValidationError(
                        explain_file_target_error(
                            repository,
                            repository_rel_path,
                            str(exc),
                            tool_name="can_i_do_this",
                        )
                    ) from exc

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

        return self._with_read_only_repository(repository_path, _callback, tool_name="can_i_do_this")

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
                explain_file_target_error(repository, repository_rel_path, str(exc), tool_name="get_file_owner")
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
        include_reference_sites: bool,
        include_implementation_locations: bool,
        enable_implementation_flow: bool,
        enable_hot_entrypoints: bool,
        reference_site_limit: int | None,
        evidence_tier: CodeEvidenceTier,
    ) -> FileUnderstandingTargetView:
        def _build_target() -> FileUnderstandingTargetView:
            try:
                context = repository.describe_files(
                    (repository_rel_path,),
                    symbol_preview_limit=20,
                    test_preview_limit=related_test_limit,
                    include_reference_sites=include_reference_sites,
                    include_implementation_locations=include_implementation_locations,
                    reference_site_limit=reference_site_limit,
                    evidence_tier=evidence_tier,
                )[0]
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
                artifact_surface_summary = self._artifact_surface_summary_view(repository, repository_rel_path)
                semantic_deadline = self._semantic_enrichment_deadline(
                    evidence_tier=evidence_tier,
                    repository=repository,
                    repository_rel_path=repository_rel_path,
                )
                implementation_flow_summary = (
                    None
                    if artifact_surface_summary is not None or not enable_implementation_flow
                    else self._run_semantic_enrichment_stage(
                        repository=repository,
                        repository_rel_path=repository_rel_path,
                        deadline=semantic_deadline,
                        stage_name="implementation_flow_summary",
                        build=lambda: self._implementation_flow_summary_view(
                            repository,
                            repository_rel_path,
                            detail_level=detail_level,
                        ),
                    )
                )
                frontend_proof_summary = (
                    None
                    if artifact_surface_summary is not None
                    else self._run_semantic_enrichment_stage(
                        repository=repository,
                        repository_rel_path=repository_rel_path,
                        deadline=semantic_deadline,
                        stage_name="frontend_proof_summary",
                        build=lambda: self._frontend_proof_summary_view(repository, repository_rel_path),
                    )
                )
                hot_entrypoints_preview = (
                    tuple()
                    if not enable_hot_entrypoints
                    else self._run_semantic_enrichment_stage(
                        repository=repository,
                        repository_rel_path=repository_rel_path,
                        deadline=semantic_deadline,
                        stage_name="hot_entrypoints_preview",
                        build=lambda: self._hot_entrypoints_preview(
                            repository,
                            repository_rel_path,
                            detail_level=detail_level,
                            deadline=semantic_deadline,
                        ),
                    )
                )
            except ValueError as exc:
                raise McpValidationError(
                    explain_file_target_error(repository, repository_rel_path, str(exc), tool_name="understand_file")
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
                hot_entrypoints_preview=hot_entrypoints_preview,
                implementation_flow_summary=implementation_flow_summary,
                frontend_proof_summary=frontend_proof_summary,
                artifact_surface_summary=artifact_surface_summary,
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
                    implementation_flow_summary.provenance if implementation_flow_summary is not None else tuple(),
                    structured_artifact_view.provenance if structured_artifact_view is not None else tuple(),
                ),
            )

        return self._with_semantic_runtime_retries(
            tool_name="understand_file",
            build_target=_build_target,
        )

    def _collect_understand_file_targets(
        self,
        *,
        repository: Repository,
        repository_rel_paths: tuple[str, ...],
        related_test_limit: int,
        detail_level: str,
        include_reference_sites: bool,
        include_implementation_locations: bool,
        enable_implementation_flow: bool,
        enable_hot_entrypoints: bool,
        reference_site_limit: int | None,
        evidence_tier: CodeEvidenceTier,
    ) -> tuple[tuple[FileUnderstandingTargetView, ...], tuple[IncompleteBatchTargetView, ...]]:
        def _build(repository_rel_path: str) -> FileUnderstandingTargetView:
            return self._understand_file_target(
                repository,
                repository_rel_path,
                related_test_limit=related_test_limit,
                detail_level=detail_level,
                include_reference_sites=include_reference_sites,
                include_implementation_locations=include_implementation_locations,
                enable_implementation_flow=enable_implementation_flow,
                enable_hot_entrypoints=enable_hot_entrypoints,
                reference_site_limit=reference_site_limit,
                evidence_tier=evidence_tier,
            )

        return self._collect_batch_results(
            repository_rel_paths=repository_rel_paths,
            build_target=_build,
            tool_name="understand_file",
            detail_level=detail_level,
            allow_parallel=self._should_parallelize_batch(detail_level, len(repository_rel_paths)),
        )

    def _collect_change_impact_targets(
        self,
        *,
        repository: Repository,
        repository_rel_paths: tuple[str, ...],
        detail_level: str,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
        include_reference_locations: bool,
        include_implementation_locations: bool,
        evidence_tier: CodeEvidenceTier,
        enable_deep_symbol_navigation: bool,
    ) -> tuple[tuple[BatchChangeImpactTargetView, ...], tuple[IncompleteBatchTargetView, ...]]:
        def _build(repository_rel_path: str) -> BatchChangeImpactTargetView:
            def _build_target() -> BatchChangeImpactTargetView:
                try:
                    impact = repository.analyze_change(
                        ChangeTarget(repository_rel_path=repository_rel_path),
                        reference_preview_limit=reference_preview_limit,
                        dependent_preview_limit=dependent_preview_limit,
                        test_preview_limit=test_preview_limit,
                        runner_preview_limit=runner_preview_limit,
                        include_reference_locations=include_reference_locations,
                        include_implementation_locations=include_implementation_locations,
                        evidence_tier=evidence_tier,
                    )
                except ValueError as exc:
                    raise McpValidationError(
                        explain_file_target_error(
                            repository,
                            repository_rel_path,
                            str(exc),
                            tool_name="what_changes_if_i_edit_this",
                        )
                    ) from exc
                artifact_surface_summary = self._artifact_surface_summary_view(repository, repository_rel_path)
                semantic_deadline = self._semantic_enrichment_deadline(
                    evidence_tier=evidence_tier,
                    repository=repository,
                    repository_rel_path=repository_rel_path,
                )
                return BatchChangeImpactTargetView(
                    repository_rel_path=repository_rel_path,
                    impact=self._change_impact_presenter.change_impact_view(impact),
                    implementation_flow_summary=(
                        None
                        if not enable_deep_symbol_navigation or artifact_surface_summary is not None
                        else self._run_semantic_enrichment_stage(
                            repository=repository,
                            repository_rel_path=repository_rel_path,
                            deadline=semantic_deadline,
                            stage_name="implementation_flow_summary",
                            build=lambda: self._implementation_flow_summary_view(
                                repository,
                                repository_rel_path,
                                detail_level=detail_level,
                            ),
                        )
                    ),
                    frontend_proof_summary=(
                        None
                        if artifact_surface_summary is not None
                        else self._run_semantic_enrichment_stage(
                            repository=repository,
                            repository_rel_path=repository_rel_path,
                            deadline=semantic_deadline,
                            stage_name="frontend_proof_summary",
                            build=lambda: self._frontend_proof_summary_view(repository, repository_rel_path),
                        )
                    ),
                    artifact_surface_summary=artifact_surface_summary,
                )

            return self._with_semantic_runtime_retries(
                tool_name="what_changes_if_i_edit_this",
                build_target=_build_target,
            )

        return self._collect_batch_results(
            repository_rel_paths=repository_rel_paths,
            build_target=_build,
            tool_name="what_changes_if_i_edit_this",
            detail_level=detail_level,
            allow_parallel=self._should_parallelize_batch(detail_level, len(repository_rel_paths)),
        )

    def _collect_batch_results(
        self,
        *,
        repository_rel_paths: tuple[str, ...],
        build_target: Callable[[str], T],
        tool_name: str,
        detail_level: str,
        allow_parallel: bool,
    ) -> tuple[tuple[T, ...], tuple[IncompleteBatchTargetView, ...]]:
        if not allow_parallel:
            completed: list[T] = []
            for repository_rel_path in repository_rel_paths:
                completed.append(build_target(repository_rel_path))
            return tuple(completed), tuple()

        executor = ThreadPoolExecutor(
            max_workers=min(self._BATCH_COMPACT_MAX_WORKERS, len(repository_rel_paths)),
            thread_name_prefix="suitcode-batch",
        )
        future_to_path: dict[Future[T], str] = {}
        try:
            for repository_rel_path in repository_rel_paths:
                future_to_path[executor.submit(build_target, repository_rel_path)] = repository_rel_path
            done, not_done = wait(
                tuple(future_to_path),
                timeout=self._BATCH_COMPACT_TARGET_TIMEOUT_SECONDS,
            )
            completed_by_path: dict[str, T] = {}
            incomplete_by_path: dict[str, IncompleteBatchTargetView] = {}
            for future in done:
                repository_rel_path = future_to_path[future]
                try:
                    completed_by_path[repository_rel_path] = future.result()
                except Exception as exc:  # noqa: BLE001
                    incomplete_by_path[repository_rel_path] = self._incomplete_batch_target_view(
                        repository_rel_path,
                        reason_code="analysis_failed",
                        message=f"{tool_name} failed for `{repository_rel_path}`: {exc}",
                    )
            for future in not_done:
                repository_rel_path = future_to_path[future]
                incomplete_by_path[repository_rel_path] = self._incomplete_batch_target_view(
                    repository_rel_path,
                    reason_code="analysis_timeout",
                    message=(
                        f"{tool_name} exceeded the grouped {detail_level} per-target timeout of "
                        f"{int(self._BATCH_COMPACT_TARGET_TIMEOUT_SECONDS)}s for `{repository_rel_path}`"
                    ),
                )
            completed_targets = tuple(
                completed_by_path[path] for path in repository_rel_paths if path in completed_by_path
            )
            incomplete_targets = tuple(
                incomplete_by_path[path] for path in repository_rel_paths if path in incomplete_by_path
            )
            return completed_targets, incomplete_targets
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _validate_detail_level(detail_level: str) -> str:
        normalized = detail_level.strip().lower()
        if normalized not in {"compact", "standard", "full"}:
            raise McpValidationError("detail_level must be one of: compact, standard, full")
        return normalized

    @staticmethod
    def _validate_detail_scope(*, tool_name: str, detail_level: str, target_count: int) -> None:
        if detail_level == "standard" and target_count > SuitMcpService._STANDARD_MAX_TARGETS:
            raise McpValidationError(
                f"{tool_name} detail_level=standard supports at most {SuitMcpService._STANDARD_MAX_TARGETS} targets. "
                "Narrow the request or use detail_level=compact for broader change-set orientation."
            )
        if detail_level == "full" and target_count > SuitMcpService._FULL_MAX_TARGETS:
            raise McpValidationError(
                f"{tool_name} detail_level=full supports exactly {SuitMcpService._FULL_MAX_TARGETS} target at a time. "
                "Narrow the request to one file or use detail_level=compact/standard first."
            )

    @classmethod
    def _should_degrade_compact_single_target(
        cls,
        repository: Repository,
        repository_rel_paths: tuple[str, ...],
        *,
        detail_level: str,
    ) -> bool:
        if detail_level != "compact" or len(repository_rel_paths) != 1:
            return False
        repository_rel_path = repository_rel_paths[0]
        try:
            file_info = repository.get_file_owner(repository_rel_path).file_info
        except ValueError:
            return False
        if file_info.language is None:
            return False
        file_path = repository.root / repository_rel_path
        if not file_path.is_file():
            return False
        try:
            line_count = 0
            byte_count = 0
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    byte_count += len(chunk)
                    line_count += chunk.count(b"\n")
                    if (
                        byte_count > cls._COMPACT_SINGLE_TARGET_STRUCTURAL_BYTE_THRESHOLD
                        or line_count > cls._COMPACT_SINGLE_TARGET_STRUCTURAL_LINE_THRESHOLD
                    ):
                        return True
        except OSError:
            return False
        return False

    @staticmethod
    def _detail_preview_limit(detail_level: str, requested_limit: int) -> int:
        if detail_level == "compact":
            return min(requested_limit, 3)
        if detail_level == "standard":
            return min(requested_limit, 10)
        return requested_limit

    @staticmethod
    def _code_evidence_tier(detail_level: str, target_count: int) -> CodeEvidenceTier:
        if detail_level == "compact" and target_count > 1:
            return CodeEvidenceTier.STRUCTURAL
        return CodeEvidenceTier.SEMANTIC

    @staticmethod
    def _should_enable_deep_symbol_navigation(detail_level: str, target_count: int) -> bool:
        if detail_level == "compact":
            return target_count == 1
        if detail_level == "standard":
            return target_count <= SuitMcpService._STANDARD_MAX_TARGETS
        return True

    @staticmethod
    def _should_parallelize_batch(detail_level: str, target_count: int) -> bool:
        if detail_level == "compact":
            return target_count > 1
        return False

    @staticmethod
    def _incomplete_batch_target_view(
        repository_rel_path: str,
        *,
        reason_code: str,
        message: str,
    ) -> IncompleteBatchTargetView:
        return IncompleteBatchTargetView(
            repository_rel_path=repository_rel_path,
            reason_code=reason_code,
            message=message,
        )

    @staticmethod
    def _compact_invariant_findings(invariant_findings):
        return tuple(item for item in invariant_findings if item.producer_site_count > 0)

    @staticmethod
    def _is_ui_heavy_path(repository_rel_path: str) -> bool:
        normalized = repository_rel_path.replace("\\", "/").lower()
        return normalized.endswith((".tsx", ".jsx"))

    @staticmethod
    def _is_frontend_source_path(repository_rel_path: str) -> bool:
        normalized = repository_rel_path.replace("\\", "/").lower()
        return normalized.endswith((".tsx", ".jsx", ".ts", ".js", ".mts", ".cts", ".mjs", ".cjs"))

    @classmethod
    def _is_frontend_npm_file_target(cls, repository: Repository, repository_rel_path: str) -> bool:
        if not cls._is_frontend_source_path(repository_rel_path):
            return False
        if cls._artifact_member_context(repository, repository_rel_path) is not None:
            return False
        try:
            owner = repository.get_file_owner(repository_rel_path).owner
        except ValueError:
            return False
        return owner.kind == "component" and owner.id.startswith("component:npm:")

    @staticmethod
    def _normalized_repository_rel_path(repository_rel_path: str) -> str:
        return repository_rel_path.replace("\\", "/").strip().removeprefix("./")

    @classmethod
    def _artifact_member_context(
        cls,
        repository: Repository,
        repository_rel_path: str,
    ) -> tuple[str, str] | None:
        normalized = cls._normalized_repository_rel_path(repository_rel_path)
        try:
            owner = repository.get_file_owner(normalized).owner
        except ValueError:
            return None
        if owner.kind != "component":
            return None
        component = next((item for item in repository.arch.get_components() if item.id == owner.id), None)
        if component is None:
            return None
        if any(normalized == root or normalized.startswith(f"{root}/") for root in component.source_roots):
            return None
        matching_roots = tuple(
            path
            for path in component.artifact_paths
            if normalized == path or normalized.startswith(f"{path}/")
        )
        if not matching_roots:
            return None
        artifact_root = max(matching_roots, key=len)
        if artifact_root != normalized and "/" in normalized:
            artifact_root = normalized.rsplit("/", 1)[0]
        return component.id, artifact_root

    @classmethod
    def _artifact_surface_summary_view(
        cls,
        repository: Repository,
        repository_rel_path: str,
    ) -> ArtifactSurfaceSummaryView | None:
        artifact_context = cls._artifact_member_context(repository, repository_rel_path)
        if artifact_context is None:
            return None
        owner_component_id, artifact_root = artifact_context
        return ArtifactSurfaceSummaryView(
            owner_component_id=owner_component_id,
            artifact_root=artifact_root,
            repository_rel_path=cls._normalized_repository_rel_path(repository_rel_path),
            quality_relevant=False,
        )

    @staticmethod
    def _is_hot_entrypoint_candidate(kind: str) -> bool:
        normalized = kind.strip().lower()
        return normalized in {"function", "method", "struct", "interface", "type", "class"}

    @staticmethod
    def _hot_entrypoint_rank_key(item: HotEntrypointView) -> tuple[int, int, int, int]:
        exported = int(bool(item.name) and item.name[:1].isupper())
        return (-int(item.external_reference_count > 0), -item.external_reference_count, -exported, item.line_start or 10**9)

    def _hot_entrypoints_preview(
        self,
        repository: Repository,
        repository_rel_path: str,
        *,
        detail_level: str,
        deadline: float | None = None,
    ) -> tuple[HotEntrypointView, ...]:
        symbols = repository.code.list_symbols_in_file(repository_rel_path)
        if len(symbols) < 20:
            return tuple()
        candidates = [item for item in symbols if self._is_hot_entrypoint_candidate(item.entity_kind)]
        if not candidates:
            return tuple()
        preview_limit = 3 if detail_level == "compact" else 5
        hot_entrypoints: list[HotEntrypointView] = []
        for symbol in candidates:
            self._ensure_semantic_stage_within_budget(
                repository=repository,
                repository_rel_path=repository_rel_path,
                deadline=deadline,
                stage_name="hot_entrypoints_preview",
            )
            references = repository.code.find_references_by_symbol_id(symbol.id)
            external_reference_count = sum(1 for location in references if location.repository_rel_path != repository_rel_path)
            hot_entrypoints.append(
                HotEntrypointView(
                    symbol_id=symbol.id,
                    name=symbol.name,
                    kind=symbol.entity_kind,
                    path=symbol.repository_rel_path,
                    line_start=symbol.line_start,
                    external_reference_count=external_reference_count,
                )
            )
            self._ensure_semantic_stage_within_budget(
                repository=repository,
                repository_rel_path=repository_rel_path,
                deadline=deadline,
                stage_name="hot_entrypoints_preview",
            )
        ranked = sorted(hot_entrypoints, key=self._hot_entrypoint_rank_key)
        return tuple(ranked[:preview_limit])

    def _frontend_proof_summary_view(
        self,
        repository: Repository,
        repository_rel_path: str,
    ) -> FrontendProofSummaryView | None:
        if not self._is_frontend_npm_file_target(repository, repository_rel_path):
            return None
        change_set = repository.get_minimum_verified_change_set(ChangeTarget(repository_rel_path=repository_rel_path))
        change_set_view = self._change_impact_presenter.minimum_verified_change_set_view(change_set)
        proof_items = tuple(
            item
            for item in change_set_view.compact_summary.required_validation
            if item.item_kind in {"test_target", "build_target", "quality_operation"}
        )[:3]
        build_proof_facets = tuple(
            sorted(
                {
                    facet
                    for item in change_set_view.build_targets
                    for facet in item.proof_facets
                }
            )
        )
        boundaries = tuple(
            MinimumVerifiedCompactItemView(
                item_kind=item.item_kind,
                item_id=item.item_id,
                summary=item.reason,
            )
            for item in change_set_view.excluded_items
            if item.reason_code == "no_deterministic_test_targets_available"
        )[:1]
        if not proof_items and not boundaries:
            return None
        return FrontendProofSummaryView(
            proof_item_count=len(proof_items),
            proof_items=proof_items,
            build_proof_facets=build_proof_facets,
            boundary_count=len(boundaries),
            boundaries=boundaries,
        )

    def _implementation_flow_summary_view(
        self,
        repository: Repository,
        repository_rel_path: str,
        *,
        detail_level: str,
    ):
        summary = repository.get_file_implementation_flow_summary(
            repository_rel_path,
            detail_level=detail_level,
        )
        if summary is None:
            return None
        return self._intelligence_presenter.implementation_flow_summary_view(summary)

    def _semantic_enrichment_deadline(
        self,
        *,
        evidence_tier: CodeEvidenceTier,
        repository: Repository,
        repository_rel_path: str,
    ) -> float | None:
        return None

    def _semantic_enrichment_budget_seconds(self, repository: Repository, repository_rel_path: str) -> float:
        return 0.0

    def _run_semantic_enrichment_stage(
        self,
        *,
        repository: Repository,
        repository_rel_path: str,
        deadline: float | None,
        stage_name: str,
        build: Callable[[], T],
    ) -> T:
        self._ensure_semantic_stage_within_budget(
            repository=repository,
            repository_rel_path=repository_rel_path,
            deadline=deadline,
            stage_name=stage_name,
        )
        result = build()
        self._ensure_semantic_stage_within_budget(
            repository=repository,
            repository_rel_path=repository_rel_path,
            deadline=deadline,
            stage_name=stage_name,
        )
        return result

    def _ensure_semantic_stage_within_budget(
        self,
        *,
        repository: Repository,
        repository_rel_path: str,
        deadline: float | None,
        stage_name: str,
    ) -> None:
        if deadline is None:
            return
        if time.monotonic() < deadline:
            return
        raise SemanticQueryTimeoutError(
            server_name=self._semantic_server_name_for_path(repository_rel_path),
            attachment_root=self._semantic_attachment_root_for_path(repository, repository_rel_path),
            state="degraded",
        ) from TimeoutError(f"semantic enrichment stage `{stage_name}` exceeded budget")

    @staticmethod
    def _semantic_server_name_for_path(repository_rel_path: str) -> str:
        lowered = repository_rel_path.lower()
        if lowered.endswith(".py"):
            return "basedpyright"
        if lowered.endswith(".go"):
            return "gopls"
        return "typescript-language-server"

    @staticmethod
    def _semantic_attachment_root_for_path(repository: Repository, repository_rel_path: str) -> str:
        providers = repository.get_providers_for_file_role(repository_rel_path, ProviderRole.CODE)
        if not providers:
            return str(repository.root)
        return str(providers[0].attachment.attachment_root)

    @staticmethod
    def _implementation_flow_paths(summary) -> set[str]:
        if summary is None:
            return set()
        return {item.path for item in summary.steps_preview}

    @staticmethod
    def _implementation_flow_render_keys(summary) -> set[tuple[str, int, int, str | None]]:
        if summary is None:
            return set()
        return {
            (item.path, item.line_start, item.column_start, item.detail_label)
            for item in summary.steps_preview
            if item.step_kind in {"prop_edge", "render_edge"}
        }

    @staticmethod
    def _implementation_flow_local_flow_keys(summary) -> set[tuple[str, int, int, str, str]]:
        if summary is None:
            return set()
        return {
            (item.path, item.line_start, item.column_start, item.source_label, item.target_label or "")
            for item in summary.steps_preview
            if item.step_kind == "local_flow_edge"
        }

    @classmethod
    def _filter_render_edges_for_summary(cls, items, summary, *, limit: int):
        blocked_keys = cls._implementation_flow_render_keys(summary)
        if not blocked_keys:
            return items[:limit]
        filtered = []
        for item in items:
            detail_label = cls._render_edge_detail_label(item)
            key = (item.path, item.line_start, item.column_start, detail_label)
            if key in blocked_keys:
                continue
            filtered.append(item)
            if len(filtered) >= limit:
                break
        return tuple(filtered)

    @classmethod
    def _filter_local_flow_edges_for_summary(cls, items, summary, *, limit: int):
        blocked_keys = cls._implementation_flow_local_flow_keys(summary)
        if not blocked_keys:
            return items[:limit]
        filtered = []
        for item in items:
            key = (item.path, item.line_start, item.column_start, item.source_label, item.target_label)
            if key in blocked_keys:
                continue
            filtered.append(item)
            if len(filtered) >= limit:
                break
        return tuple(filtered)

    @staticmethod
    def _render_edge_detail_label(item) -> str | None:
        details: list[str] = []
        if item.prop_names:
            details.append(", ".join(item.prop_names[:4]))
        if item.has_spread_props:
            details.append("spread props")
        return "; ".join(details) or None

    @staticmethod
    def _compact_file_target_limits(
        *,
        ui_heavy: bool,
        multi_target: bool,
        has_flow_summary: bool,
    ) -> dict[str, int]:
        limits = {
            "reference": 3,
            "render": 2 if ui_heavy else 3,
            "dependency": 1 if ui_heavy else 3,
            "dependent": 2 if ui_heavy else 3,
            "invariant": 1 if ui_heavy else 3,
            "local_flow": 1 if ui_heavy else 3,
            "related_tests": 3,
        }
        if multi_target:
            limits.update(
                {
                    "reference": 1,
                    "render": 1,
                    "dependency": 1,
                    "dependent": 1,
                    "invariant": 1,
                    "local_flow": 1,
                    "related_tests": 1,
                }
            )
        if has_flow_summary:
            limits["render"] = min(limits["render"], 1)
            limits["dependency"] = min(limits["dependency"], 1)
            limits["dependent"] = min(limits["dependent"], 1)
            limits["local_flow"] = min(limits["local_flow"], 1)
        return limits

    @staticmethod
    def _compact_change_target_limits(
        *,
        ui_heavy: bool,
        multi_target: bool,
        has_flow_summary: bool,
    ) -> dict[str, int]:
        limits = {
            "reference": 3,
            "render": 2 if ui_heavy else 3,
            "dependent": 2 if ui_heavy else 3,
            "invariant": 1 if ui_heavy else 3,
            "local_flow": 1 if ui_heavy else 3,
            "related_tests": 3,
            "components": 3,
            "quality_gates": 3,
            "runners": 3,
        }
        if multi_target:
            limits.update(
                {
                    "reference": 1,
                    "render": 1,
                    "dependent": 1,
                    "invariant": 1,
                    "local_flow": 1,
                    "related_tests": 1,
                    "components": 1,
                    "quality_gates": 1,
                    "runners": 1,
                }
            )
        if has_flow_summary:
            limits["render"] = min(limits["render"], 1)
            limits["dependent"] = min(limits["dependent"], 1)
            limits["local_flow"] = min(limits["local_flow"], 1)
        return limits

    @classmethod
    def _is_ui_heavy_file_target(cls, target: FileUnderstandingTargetView) -> bool:
        return (
            cls._is_ui_heavy_path(target.repository_rel_path)
            or bool(target.render_children_preview)
            or bool(target.render_parents_preview)
        )

    @classmethod
    def _is_ui_heavy_change_target(cls, target: BatchChangeImpactTargetView) -> bool:
        return (
            cls._is_ui_heavy_path(target.repository_rel_path)
            or bool(target.impact.render_children)
            or bool(target.impact.render_parents)
        )

    @staticmethod
    def _filter_relationship_paths(items, *, blocked_paths: set[str], limit: int) -> tuple:
        filtered = []
        seen: set[str] = set()
        for item in items:
            if item.path in blocked_paths or item.path in seen:
                continue
            seen.add(item.path)
            filtered.append(item)
            if len(filtered) >= limit:
                break
        return tuple(filtered)

    @staticmethod
    def _render_paths(*groups) -> set[str]:
        return {item.path for group in groups for item in group}

    @staticmethod
    def _location_paths(*groups) -> set[str]:
        return {item.path for group in groups for item in group}

    @staticmethod
    def _owner_round_robin_targets(targets, owner_getter):
        grouped = defaultdict(deque)
        owner_order: list[str] = []
        for target in targets:
            owner_id = owner_getter(target)
            if owner_id not in grouped:
                owner_order.append(owner_id)
            grouped[owner_id].append(target)
        ordered = []
        remaining = True
        while remaining:
            remaining = False
            for owner_id in owner_order:
                if not grouped[owner_id]:
                    continue
                ordered.append(grouped[owner_id].popleft())
                remaining = True
        return tuple(ordered)

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
        repository: Repository,
        targets: tuple[FileUnderstandingTargetView, ...],
        *,
        target_count: int | None = None,
        incomplete_targets: tuple[IncompleteBatchTargetView, ...] = (),
    ) -> FileUnderstandingCompactView:
        multi_target = len(targets) > 1
        compact_targets = tuple(
            self._compact_file_target_view(
                repository,
                target,
                multi_target=multi_target,
                has_partial_batch=bool(incomplete_targets),
            )
            for target in (
                self._owner_round_robin_targets(targets, lambda item: item.file_owner.owner.id)
                if multi_target
                else targets
            )
        )
        return FileUnderstandingCompactView(
            detail_level="compact",
            target_count=target_count if target_count is not None else len(compact_targets),
            completed_target_count=len(compact_targets),
            targets=compact_targets,
            incomplete_targets=incomplete_targets,
        )

    def _compact_file_target_view(
        self,
        repository: Repository,
        target: FileUnderstandingTargetView,
        *,
        multi_target: bool,
        has_partial_batch: bool,
    ) -> FileUnderstandingCompactTargetView:
        if target.structured_artifact is not None:
            return FileUnderstandingCompactTargetView(
                detail_level="compact",
                repository_rel_path=target.repository_rel_path,
                file_owner=target.file_owner,
                artifact_surface_summary=target.artifact_surface_summary,
                structured_artifact=target.structured_artifact,
            )
        top_dependents = self._filter_relationship_paths(
            target.dependent_files_preview,
            blocked_paths=set(),
            limit=2 if multi_target else 3,
        )
        top_validations = self._top_validations_for_path(
            repository,
            target.repository_rel_path,
            tool_name="understand_file",
            limit=2 if multi_target else 3,
        )
        blocking_invariants = self._compact_invariant_findings(target.invariant_findings_preview)[:2]
        public_surfaces = self._compact_public_boundaries_for_path(
            repository,
            repository_rel_path=target.repository_rel_path,
            language=target.file_owner.file.language,
            top_validations=top_validations,
            artifact_surface_summary=target.artifact_surface_summary,
        )
        top_risks = self._compact_risk_views(
            top_validations=top_validations,
            public_boundaries=public_surfaces,
            blocking_invariants=blocking_invariants,
            has_partial_batch=has_partial_batch,
        )
        return FileUnderstandingCompactTargetView(
            detail_level="compact",
            repository_rel_path=target.repository_rel_path,
            file_owner=target.file_owner,
            top_dependents=top_dependents,
            top_validations=top_validations,
            public_surfaces=public_surfaces,
            blocking_invariants=blocking_invariants,
            top_risks=top_risks,
            decision_summary=self._file_decision_summary(
                target,
                top_dependents=top_dependents,
                top_validations=top_validations,
                public_surfaces=public_surfaces,
                blocking_invariants=blocking_invariants,
                top_risks=top_risks,
            ),
            artifact_surface_summary=target.artifact_surface_summary,
        )

    def _top_validations_for_path(
        self,
        repository: Repository,
        repository_rel_path: str,
        *,
        tool_name: str,
        limit: int,
    ) -> tuple[MinimumVerifiedCompactItemView, ...]:
        target = self._minimum_verified_batch_target_view(
            repository,
            repository_rel_path,
            tool_name=tool_name,
        )
        return target.change_set.compact_summary.required_validation[:limit]

    def _compact_public_boundaries_for_path(
        self,
        repository: Repository,
        *,
        repository_rel_path: str,
        language: str | None,
        top_validations: tuple[MinimumVerifiedCompactItemView, ...],
        artifact_surface_summary: ArtifactSurfaceSummaryView | None,
    ) -> tuple[CompactSurfaceBoundaryView, ...]:
        boundaries: list[CompactSurfaceBoundaryView] = []
        if artifact_surface_summary is not None:
            boundaries.append(
                CompactSurfaceBoundaryView(
                    boundary_kind="public_runtime_asset",
                    boundary_id=artifact_surface_summary.artifact_root,
                    summary=f"Public runtime asset under `{artifact_surface_summary.artifact_root}`.",
                )
            )
        for item in top_validations:
            if item.item_kind == "build_target":
                boundaries.append(
                    CompactSurfaceBoundaryView(
                        boundary_kind="build_entry_surface",
                        boundary_id=item.item_id,
                        summary=item.summary,
                    )
                )
            elif item.item_kind == "runner_action":
                boundaries.append(
                    CompactSurfaceBoundaryView(
                        boundary_kind="runner_entry_surface",
                        boundary_id=item.item_id,
                        summary=item.summary,
                    )
                )
        if artifact_surface_summary is None:
            try:
                symbols = repository.code.list_symbols_in_file(repository_rel_path)
            except ValueError:
                symbols = tuple()
            for symbol in symbols:
                if not self._is_public_symbol(symbol, language):
                    continue
                boundaries.append(
                    CompactSurfaceBoundaryView(
                        boundary_kind="exported_symbol",
                        boundary_id=symbol.id,
                        summary=f"Public symbol `{symbol.name}` ({symbol.entity_kind}) in `{repository_rel_path}`.",
                    )
                )
                if len(boundaries) >= 3:
                    break
        return self._dedupe_views(
            tuple(boundaries),
            key=lambda item: (item.boundary_kind, item.boundary_id),
        )[:3]

    @staticmethod
    def _is_public_symbol(symbol, language: str | None) -> bool:
        name = getattr(symbol, "name", "").strip()
        if not name:
            return False
        normalized_language = (language or "").strip().lower()
        signature = (getattr(symbol, "signature", None) or "").strip()
        if normalized_language == "go":
            return name[:1].isupper()
        if normalized_language == "python":
            return not name.startswith("_")
        if normalized_language in {"javascript", "typescript", "jsx", "tsx"}:
            return "export " in signature
        return False

    @staticmethod
    def _compact_risk_views(
        *,
        top_validations: tuple[MinimumVerifiedCompactItemView, ...],
        public_boundaries: tuple[CompactSurfaceBoundaryView, ...],
        blocking_invariants: tuple[InvariantFindingView, ...],
        has_partial_batch: bool,
    ) -> tuple[CompactRiskView, ...]:
        risks: list[CompactRiskView] = []
        if not top_validations:
            risks.append(
                CompactRiskView(
                    risk_code="no_deterministic_validation_surface",
                    summary="No deterministic validation surface was identified for this target.",
                )
            )
        elif all(item.item_kind == "build_target" for item in top_validations):
            risks.append(
                CompactRiskView(
                    risk_code="build_only_validation",
                    summary="Current deterministic proof bottoms out at build-only validation.",
                )
            )
        if blocking_invariants:
            risks.append(
                CompactRiskView(
                    risk_code="blocking_invariant_present",
                    summary="Blocking invariants were detected and may constrain safe edits.",
                )
            )
        if public_boundaries:
            risks.append(
                CompactRiskView(
                    risk_code="public_surface_touched",
                    summary="This target touches a public or entry boundary with wider blast radius.",
                )
            )
        if has_partial_batch:
            risks.append(
                CompactRiskView(
                    risk_code="grouped_partial_result",
                    summary="Grouped compact results are partial because at least one sibling target did not complete.",
                )
            )
        return tuple(risks)

    def _file_decision_summary(
        self,
        target: FileUnderstandingTargetView,
        *,
        top_dependents: tuple[FileRelationshipView, ...],
        top_validations: tuple[MinimumVerifiedCompactItemView, ...],
        public_surfaces: tuple[CompactSurfaceBoundaryView, ...],
        blocking_invariants: tuple[InvariantFindingView, ...],
        top_risks: tuple[CompactRiskView, ...],
    ) -> tuple[str, ...]:
        statements = [
            f"Owned by {target.file_owner.owner.kind} `{target.file_owner.owner.name}`.",
            (
                f"{len(top_dependents)} closest dependent files were kept in the compact planning surface."
                if top_dependents
                else "No close dependent files were surfaced in the compact planning surface."
            ),
            self._validation_summary_statement(top_validations),
        ]
        if public_surfaces:
            statements.append(f"{len(public_surfaces)} public or entry surfaces are directly touched.")
        if blocking_invariants:
            statements.append(f"{len(blocking_invariants)} blocking invariants were retained for planning.")
        elif top_risks:
            statements.append(top_risks[0].summary)
        return tuple(statements[:5])

    def _change_decision_summary(
        self,
        target: BatchChangeImpactTargetView,
        *,
        top_impacted_files: tuple[FileRelationshipView, ...],
        top_validations: tuple[MinimumVerifiedCompactItemView, ...],
        api_or_public_boundaries: tuple[CompactSurfaceBoundaryView, ...],
        top_risks: tuple[CompactRiskView, ...],
    ) -> tuple[str, ...]:
        owner_label = target.impact.primary_component.name if target.impact.primary_component else target.impact.owner.name
        statements = [
            f"Primary owner surface is `{owner_label}`.",
            (
                f"{len(top_impacted_files)} highest-signal impacted files were retained."
                if top_impacted_files
                else "No close impacted files were retained in compact mode."
            ),
            self._validation_summary_statement(top_validations),
        ]
        if api_or_public_boundaries:
            statements.append(f"{len(api_or_public_boundaries)} API or public boundaries are part of the blast radius.")
        if top_risks:
            statements.append(top_risks[0].summary)
        return tuple(statements[:5])

    @staticmethod
    def _validation_summary_statement(top_validations: tuple[MinimumVerifiedCompactItemView, ...]) -> str:
        if not top_validations:
            return "No deterministic validation surface was identified."
        if len(top_validations) == 1:
            return f"Closest deterministic validation: {top_validations[0].summary}"
        return f"{len(top_validations)} deterministic validation surfaces were retained."

    @staticmethod
    def _change_target_language(target: BatchChangeImpactTargetView) -> str | None:
        component = target.impact.primary_component
        return component.language if component is not None else None

    def _standard_file_understanding_view(
        self,
        targets: tuple[FileUnderstandingTargetView, ...],
        *,
        target_count: int | None = None,
        incomplete_targets: tuple[IncompleteBatchTargetView, ...] = (),
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
                hot_entrypoints_preview=target.hot_entrypoints_preview[:5],
                implementation_flow_summary=target.implementation_flow_summary,
                frontend_proof_summary=target.frontend_proof_summary,
                artifact_surface_summary=target.artifact_surface_summary,
                structured_artifact=target.structured_artifact,
            )
            for target in targets
        )
        return FileUnderstandingStandardView(
            detail_level="standard",
            target_count=target_count if target_count is not None else len(standard_targets),
            completed_target_count=len(standard_targets),
            targets=standard_targets,
            incomplete_targets=incomplete_targets,
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
        repository: Repository,
        targets: tuple[BatchChangeImpactTargetView, ...],
        *,
        target_count: int | None = None,
        incomplete_targets: tuple[IncompleteBatchTargetView, ...] = (),
    ) -> BatchChangeImpactCompactView:
        multi_target = len(targets) > 1
        compact_targets = tuple(
            self._compact_change_target_view(
                repository,
                target,
                multi_target=multi_target,
                has_partial_batch=bool(incomplete_targets),
            )
            for target in (
                self._owner_round_robin_targets(targets, lambda item: item.impact.owner.id)
                if multi_target
                else targets
            )
        )
        return BatchChangeImpactCompactView(
            detail_level="compact",
            target_count=target_count if target_count is not None else len(compact_targets),
            completed_target_count=len(compact_targets),
            targets=compact_targets,
            incomplete_targets=incomplete_targets,
        )

    def _compact_change_target_view(
        self,
        repository: Repository,
        target: BatchChangeImpactTargetView,
        *,
        multi_target: bool,
        has_partial_batch: bool,
    ) -> BatchChangeImpactCompactTargetView:
        top_impacted_files = self._filter_relationship_paths(
            target.impact.dependent_files,
            blocked_paths=set(),
            limit=2 if multi_target else 3,
        )
        top_validations = self._top_validations_for_path(
            repository,
            target.repository_rel_path,
            tool_name="what_changes_if_i_edit_this",
            limit=2 if multi_target else 3,
        )
        api_or_public_boundaries = self._compact_public_boundaries_for_path(
            repository,
            repository_rel_path=target.repository_rel_path,
            language=self._change_target_language(target),
            top_validations=top_validations,
            artifact_surface_summary=target.artifact_surface_summary,
        )
        top_risks = self._compact_risk_views(
            top_validations=top_validations,
            public_boundaries=api_or_public_boundaries,
            blocking_invariants=self._compact_invariant_findings(target.impact.invariant_findings)[:2],
            has_partial_batch=has_partial_batch,
        )
        return BatchChangeImpactCompactTargetView(
            detail_level="compact",
            repository_rel_path=target.repository_rel_path,
            owner=target.impact.owner,
            primary_component=target.impact.primary_component,
            top_impacted_files=top_impacted_files,
            top_validations=top_validations,
            api_or_public_boundaries=api_or_public_boundaries,
            top_risks=top_risks,
            decision_summary=self._change_decision_summary(
                target,
                top_impacted_files=top_impacted_files,
                top_validations=top_validations,
                api_or_public_boundaries=api_or_public_boundaries,
                top_risks=top_risks,
            ),
            artifact_surface_summary=target.artifact_surface_summary,
        )

    def _standard_change_impact_view(
        self,
        targets: tuple[BatchChangeImpactTargetView, ...],
        *,
        target_count: int | None = None,
        incomplete_targets: tuple[IncompleteBatchTargetView, ...] = (),
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
                implementation_flow_summary=target.implementation_flow_summary,
                frontend_proof_summary=target.frontend_proof_summary,
                artifact_surface_summary=target.artifact_surface_summary,
            )
            for target in targets
        )
        return BatchChangeImpactStandardView(
            detail_level="standard",
            target_count=target_count if target_count is not None else len(standard_targets),
            completed_target_count=len(standard_targets),
            targets=standard_targets,
            incomplete_targets=incomplete_targets,
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
            "no_deterministic_validation_surface_for_artifact_member",
            "no_deterministic_validation_surfaces_for_provider_owned_artifact",
            "no_narrower_direct_validation_surface_for_file_target",
        }
        return tuple(item for item in excluded_items if item.reason_code in allowed_reason_codes)

    def _with_read_only_repository(
        self,
        repository_path: str,
        callback: Callable[[Repository], T],
        *,
        tool_name: str,
    ) -> T:
        try:
            repository = self._read_only_registry.open_repository(repository_path).repository
            return self._with_semantic_runtime_retries(
                tool_name=tool_name,
                build_target=lambda: callback(repository),
            )
        except (McpNotFoundError, McpValidationError, McpUnsupportedRepositoryError, McpRetryableError):
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
        seen: set[tuple[object, ...]] = set()
        for group in groups:
            for entry in group:
                key = (
                    entry.confidence_mode,
                    entry.source_kind,
                    entry.source_tool,
                    entry.evidence_summary,
                    entry.evidence_paths,
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(entry)
        return tuple(merged)

    def _with_semantic_runtime_retries(
        self,
        *,
        tool_name: str,
        build_target: Callable[[], T],
    ) -> T:
        started_at = time.monotonic()
        total_sleep_seconds = 0.0
        last_retryable_exc = None
        max_attempts = self._SEMANTIC_RUNTIME_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
            try:
                return build_target()
            except (CoordinatorRuntimeNotReadyError, TypeScriptToolTimeoutError, SemanticQueryTimeoutError) as exc:
                last_retryable_exc = exc
                if attempt >= max_attempts:
                    break
                elapsed_seconds = time.monotonic() - started_at
                remaining_sleep_budget = max(
                    0.0,
                    self._SEMANTIC_RUNTIME_MAX_TOTAL_RETRY_SLEEP_SECONDS - total_sleep_seconds,
                )
                remaining_wall_budget = max(
                    0.0,
                    self._SEMANTIC_RUNTIME_MAX_TOTAL_WALL_CLOCK_SECONDS - elapsed_seconds,
                )
                if remaining_sleep_budget <= 0.0 or remaining_wall_budget <= 0.0:
                    break
                requested_sleep_seconds = float(max(0, getattr(exc, "retry_after_seconds", 0) or 0))
                sleep_seconds = min(
                    requested_sleep_seconds,
                    remaining_sleep_budget,
                    remaining_wall_budget,
                )
                if sleep_seconds <= 0.0:
                    break
                time.sleep(sleep_seconds)
                total_sleep_seconds += sleep_seconds
        if last_retryable_exc is None:
            raise RuntimeError(f"{tool_name} semantic retry wrapper exited without a retryable failure")
        raise self._runtime_not_ready_error(
            tool_name=tool_name,
            exc=last_retryable_exc,
            attempted_retries=max_attempts,
            max_attempts=max_attempts,
            retry_exhausted=True,
        ) from last_retryable_exc

    @staticmethod
    def _runtime_not_ready_error(
        *,
        tool_name: str,
        exc,
        attempted_retries: int,
        max_attempts: int,
        retry_exhausted: bool,
    ) -> McpRetryableError:
        server_name = getattr(getattr(exc, "server_family", None), "value", None) or getattr(exc, "server_name", "runtime")
        state = getattr(getattr(exc, "state", None), "value", None) or getattr(exc, "state", "degraded")
        retry_after_seconds = exc.retry_after_seconds
        return McpRetryableError(
            "runtime_not_ready: "
            f"tool={tool_name} "
            f"server={server_name} "
            f"attachment_root={exc.attachment_root} "
            f"state={state} "
            f"retry_after_seconds={retry_after_seconds} "
            f"attempted_retries={attempted_retries} "
            f"max_attempts={max_attempts} "
            f"retry_exhausted={'true' if retry_exhausted else 'false'}; "
            "SuitCode retried internally and the runtime is still not ready. "
            "Narrow to 1 target or use detail_level=compact."
        )
