from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class ListResult(StrictModel, Generic[T]):
    items: tuple[T, ...]
    limit: int
    offset: int
    total: int
    truncated: bool
    next_offset: int | None = None


class ProviderDescriptorView(StrictModel):
    provider_id: str
    display_name: str
    build_systems: tuple[str, ...]
    programming_languages: tuple[str, ...]
    supported_roles: tuple[str, ...]


class DetectedProviderView(StrictModel):
    provider_id: str
    display_name: str
    detected_roles: tuple[str, ...]
    build_systems: tuple[str, ...]
    programming_languages: tuple[str, ...]


class RepositorySupportView(StrictModel):
    repository_root: str
    is_supported: bool
    detected_providers: tuple[DetectedProviderView, ...] = Field(default_factory=tuple)


class WorkspaceView(StrictModel):
    workspace_id: str
    repository_ids: tuple[str, ...]
    repository_count: int


class RepositoryView(StrictModel):
    workspace_id: str
    repository_id: str
    root_path: str
    suit_dir: str
    provider_ids: tuple[str, ...]
    provider_roles: dict[str, tuple[str, ...]]


class OpenWorkspaceResult(StrictModel):
    workspace: WorkspaceView
    initial_repository: RepositoryView
    reused: bool


class AddRepositoryResult(StrictModel):
    workspace_id: str
    repository: RepositoryView
    owning_workspace_id: str
    reused: bool


class CloseWorkspaceResult(StrictModel):
    workspace_id: str
    closed: bool


class QualityProvidersView(StrictModel):
    provider_ids: tuple[str, ...]


class ComponentView(StrictModel):
    id: str
    name: str
    component_kind: str
    language: str
    source_roots: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class AggregatorView(StrictModel):
    id: str
    name: str
    provenance: tuple[ProvenanceView, ...]


class RunnerView(StrictModel):
    id: str
    name: str
    argv: tuple[str, ...]
    cwd: str | None = None
    provenance: tuple[ProvenanceView, ...]


class RunnerContextView(StrictModel):
    runner: RunnerView
    action_id: str
    provider_id: str
    invocation: ActionInvocationView
    primary_component: ComponentView | None = None
    owned_file_count: int
    owned_files_preview: tuple[FileView, ...]
    related_test_count: int
    related_tests_preview: tuple[RelatedTestView, ...]
    provenance: tuple[ProvenanceView, ...]


class RunnerExecutionResultView(StrictModel):
    runner_id: str
    action_id: str
    status: str
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    output_excerpt: str | None = None
    provenance: tuple[ProvenanceView, ...]


class BuildTargetDescriptionView(StrictModel):
    action_id: str
    name: str
    provider_id: str
    target_id: str
    target_kind: str
    owner_ids: tuple[str, ...]
    invocation: ActionInvocationView
    dry_run_supported: bool
    provenance: tuple[ProvenanceView, ...]


class BuildExecutionResultView(StrictModel):
    action_id: str
    target_id: str
    target_kind: str
    status: str
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    output_excerpt: str | None = None
    provenance: tuple[ProvenanceView, ...]


class BuildProjectResultView(StrictModel):
    timeout_seconds: int
    total: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    succeeded_target_ids: tuple[str, ...]
    failed_results: tuple[BuildExecutionResultView, ...]
    provenance: tuple[ProvenanceView, ...]


class PackageManagerView(StrictModel):
    id: str
    name: str
    manager: str
    lockfile_path: str | None = None
    provenance: tuple[ProvenanceView, ...]


class ExternalPackageView(StrictModel):
    id: str
    name: str
    manager_id: str | None = None
    version_spec: str | None = None
    provenance: tuple[ProvenanceView, ...]


class FileView(StrictModel):
    id: str
    path: str
    language: str | None = None
    owner_id: str
    provenance: tuple[ProvenanceView, ...]


class SymbolView(StrictModel):
    id: str
    name: str
    kind: str
    path: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    signature: str | None = None
    provenance: tuple[ProvenanceView, ...]


class LocationView(StrictModel):
    path: str
    line_start: int
    line_end: int | None = None
    column_start: int
    column_end: int | None = None
    symbol_id: str | None = None
    provenance: tuple[ProvenanceView, ...]


class OwnerView(StrictModel):
    id: str
    kind: str
    name: str


class FileOwnerView(StrictModel):
    file: FileView
    owner: OwnerView


class ProvenanceView(StrictModel):
    confidence_mode: str
    source_kind: str
    source_tool: str | None = None
    evidence_summary: str
    evidence_paths: tuple[str, ...]


class TestDefinitionView(StrictModel):
    id: str
    name: str
    framework: str
    test_files: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class RelatedTestView(StrictModel):
    id: str
    name: str
    framework: str
    test_file_count: int
    test_files_preview: tuple[str, ...]
    relation_reason: str
    matched_owner_id: str | None = None
    matched_path: str | None = None
    provenance: tuple[ProvenanceView, ...]


class TestTargetDescriptionView(StrictModel):
    id: str
    name: str
    framework: str
    test_files: tuple[str, ...]
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    is_authoritative: bool
    warning: str | None = None
    provenance: tuple[ProvenanceView, ...]


class TestFailureSnippetView(StrictModel):
    repository_rel_path: str
    line_start: int
    line_end: int
    snippet: str
    provenance: tuple[ProvenanceView, ...]


class TestExecutionResultView(StrictModel):
    test_id: str
    status: str
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    warning: str | None = None
    output_excerpt: str | None = None
    failure_snippets: tuple[TestFailureSnippetView, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceView, ...]


class RunTestTargetsView(StrictModel):
    workspace_id: str
    repository_id: str
    timeout_seconds: int
    total: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    results: tuple[TestExecutionResultView, ...]


class DependencyRefView(StrictModel):
    target_id: str
    target_kind: str
    dependency_scope: str
    provenance: tuple[ProvenanceView, ...]


class ComponentDependencyEdgeView(StrictModel):
    source_component_id: str
    target_id: str
    target_kind: str
    dependency_scope: str
    provenance: tuple[ProvenanceView, ...]


class ComponentContextView(StrictModel):
    component: ComponentView
    owned_file_count: int
    owned_files_preview: tuple[FileView, ...]
    runner_ids: tuple[str, ...]
    related_test_ids: tuple[str, ...]
    dependency_count: int
    dependencies_preview: tuple[DependencyRefView, ...]
    dependent_count: int
    dependents_preview: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class FileContextView(StrictModel):
    file: FileView
    owner: OwnerView
    symbol_count: int
    symbols_preview: tuple[SymbolView, ...]
    related_test_count: int
    related_tests_preview: tuple[RelatedTestView, ...]
    quality_provider_ids: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class SymbolContextView(StrictModel):
    symbol: SymbolView
    owner: OwnerView
    definition_count: int
    definitions: tuple[LocationView, ...]
    reference_count: int
    references_preview: tuple[LocationView, ...]
    related_test_count: int
    related_tests_preview: tuple[RelatedTestView, ...]
    provenance: tuple[ProvenanceView, ...]


class ImpactSummaryView(StrictModel):
    target_kind: str
    owner: OwnerView
    primary_component_id: str | None = None
    dependent_component_count: int
    dependent_component_ids_preview: tuple[str, ...]
    reference_count: int
    references_preview: tuple[LocationView, ...]
    related_test_count: int
    related_test_ids_preview: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class QualityGateView(StrictModel):
    provider_id: str
    provider_roles: tuple[str, ...]
    applies: bool
    reason: str
    provenance: tuple[ProvenanceView, ...]


class RunnerImpactView(StrictModel):
    runner: RunnerView
    reason: str
    provenance: tuple[ProvenanceView, ...]


class TestImpactView(StrictModel):
    test: RelatedTestView
    reason: str
    provenance: tuple[ProvenanceView, ...]


class ChangeEvidenceEdgeView(StrictModel):
    source_node_kind: str
    source_node_id: str
    target_node_kind: str
    target_node_id: str
    edge_kind: str
    reason: str
    provenance: tuple[ProvenanceView, ...]


class ChangeEvidencePreviewView(StrictModel):
    total_edges: int
    counts_by_kind: dict[str, int]
    edges_preview: tuple[ChangeEvidenceEdgeView, ...]
    truncated: bool


class ChangeImpactView(StrictModel):
    target_kind: str
    owner: OwnerView
    primary_component: ComponentView | None = None
    component_context: ComponentContextView | None = None
    file_context: FileContextView | None = None
    symbol_context: SymbolContextView | None = None
    dependent_components: tuple[ComponentView, ...]
    reference_locations: tuple[LocationView, ...]
    related_tests: tuple[TestImpactView, ...]
    related_runners: tuple[RunnerImpactView, ...]
    quality_gates: tuple[QualityGateView, ...]
    evidence: ChangeEvidencePreviewView
    truth_coverage: TruthCoverageSummaryView
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedEvidenceEdgeView(StrictModel):
    source_node_kind: str
    source_node_id: str
    target_node_kind: str
    target_node_id: str
    edge_kind: str
    reason: str
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedCommandSummaryView(StrictModel):
    argv_preview: tuple[str, ...]
    total_arg_count: int
    truncated: bool
    cwd: str | None = None


class MinimumVerifiedTestTargetView(StrictModel):
    test_id: str
    name: str
    framework: str
    test_file_count: int
    test_files_preview: tuple[str, ...]
    command: MinimumVerifiedCommandSummaryView
    is_authoritative: bool
    warning: str | None = None
    inclusion_reason: str
    inclusion_confidence_mode: str
    proof_edges: tuple[MinimumVerifiedEvidenceEdgeView, ...]
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedBuildTargetView(StrictModel):
    action_id: str
    name: str
    provider_id: str
    target_id: str
    target_kind: str
    owner_ids: tuple[str, ...]
    invocation: MinimumVerifiedCommandSummaryView
    dry_run_supported: bool
    inclusion_reason: str
    inclusion_confidence_mode: str
    proof_edges: tuple[MinimumVerifiedEvidenceEdgeView, ...]
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedRunnerActionView(StrictModel):
    action_id: str
    name: str
    provider_id: str
    target_id: str
    target_kind: str
    invocation: MinimumVerifiedCommandSummaryView
    inclusion_reason: str
    inclusion_confidence_mode: str
    proof_edges: tuple[MinimumVerifiedEvidenceEdgeView, ...]
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedQualityOperationView(StrictModel):
    id: str
    provider_id: str
    operation: str
    scope: str
    repository_rel_paths: tuple[str, ...]
    mcp_tool_name: str
    is_fix: bool | None = None
    is_mutating: bool
    inclusion_reason: str
    inclusion_confidence_mode: str
    proof_edges: tuple[MinimumVerifiedEvidenceEdgeView, ...]
    provenance: tuple[ProvenanceView, ...]


class ExcludedMinimumVerifiedItemView(StrictModel):
    item_kind: str
    item_id: str
    reason_code: str
    reason: str
    replaced_by_ids: tuple[str, ...]
    provenance: tuple[ProvenanceView, ...]


class MinimumVerifiedChangeSetView(StrictModel):
    target_kind: str
    owner: OwnerView
    primary_component: ComponentView | None = None
    tests: tuple[MinimumVerifiedTestTargetView, ...]
    build_targets: tuple[MinimumVerifiedBuildTargetView, ...]
    runner_actions: tuple[MinimumVerifiedRunnerActionView, ...]
    quality_validation_operations: tuple[MinimumVerifiedQualityOperationView, ...]
    quality_hygiene_operations: tuple[MinimumVerifiedQualityOperationView, ...]
    excluded_items: tuple[ExcludedMinimumVerifiedItemView, ...]
    provenance: tuple[ProvenanceView, ...]


class ActionInvocationView(StrictModel):
    argv: tuple[str, ...]
    cwd: str | None = None


class ActionView(StrictModel):
    id: str
    name: str
    kind: str
    provider_id: str
    target_id: str
    target_kind: str
    owner_ids: tuple[str, ...]
    invocation: ActionInvocationView
    dry_run_supported: bool
    provenance: tuple[ProvenanceView, ...]


class QualityDiagnosticView(StrictModel):
    tool: str
    severity: str
    message: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    rule_id: str | None = None
    provenance: tuple[ProvenanceView, ...]


class QualityEntityDeltaView(StrictModel):
    added: tuple[SymbolView, ...] = Field(default_factory=tuple)
    removed: tuple[SymbolView, ...] = Field(default_factory=tuple)
    updated: tuple[SymbolView, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceView, ...]


class QualityFileResultView(StrictModel):
    workspace_id: str
    repository_id: str
    provider_id: str
    repository_rel_path: str
    tool: str
    operation: str
    changed: bool
    success: bool
    message: str | None = None
    diagnostics: tuple[QualityDiagnosticView, ...] = Field(default_factory=tuple)
    entity_delta: QualityEntityDeltaView = Field(default_factory=QualityEntityDeltaView)
    applied_fixes: bool
    content_sha_before: str
    content_sha_after: str
    provenance: tuple[ProvenanceView, ...]


class WorkspaceSnapshotView(StrictModel):
    workspace_id: str
    repository_count: int
    repository_ids: tuple[str, ...]


class RepositorySnapshotView(StrictModel):
    workspace_id: str
    repository_id: str
    root_path: str
    suit_dir: str
    provider_ids: tuple[str, ...]
    provider_roles: dict[str, tuple[str, ...]]


class ArchitectureSnapshotView(StrictModel):
    workspace_id: str
    repository_id: str
    provider_ids: tuple[str, ...]
    component_count: int
    aggregator_count: int
    runner_count: int
    package_manager_count: int
    external_package_count: int
    file_count: int


class TestsSnapshotView(StrictModel):
    workspace_id: str
    repository_id: str
    provider_ids: tuple[str, ...]
    test_count: int


class QualitySnapshotView(StrictModel):
    workspace_id: str
    repository_id: str
    provider_ids: tuple[str, ...]


class TruthCoverageByDomainView(StrictModel):
    domain: str
    total_entities: int
    authoritative_count: int
    derived_count: int
    heuristic_count: int
    unavailable_count: int
    availability: str
    degraded_reason: str | None = None
    source_kind_mix: dict[str, int]
    source_tool_mix: dict[str, int]
    execution_available: bool | None = None
    action_capabilities: dict[str, bool]


class TruthCoverageSummaryView(StrictModel):
    scope_kind: str
    scope_id: str
    domains: tuple[TruthCoverageByDomainView, ...]
    overall_authoritative_count: int
    overall_derived_count: int
    overall_heuristic_count: int
    overall_unavailable_count: int
    overall_availability: str
    provenance: tuple[ProvenanceView, ...]


class RepositorySummaryView(StrictModel):
    workspace_id: str
    repository_id: str
    provider_ids: tuple[str, ...]
    provider_roles: dict[str, tuple[str, ...]]
    quality_provider_ids: tuple[str, ...]
    component_count: int
    runner_count: int
    package_manager_count: int
    external_package_count: int
    test_count: int
    file_count: int
    component_ids_preview: tuple[str, ...]
    runner_ids_preview: tuple[str, ...]
    package_manager_ids_preview: tuple[str, ...]
    test_ids_preview: tuple[str, ...]
    preview_limit: int
    truth_coverage: TruthCoverageSummaryView | None = None
    provenance: tuple[ProvenanceView, ...]


class AnalyticsSummaryView(StrictModel):
    total_calls: int
    success_calls: int
    error_calls: int
    p50_duration_ms: int
    p95_duration_ms: int
    total_payload_bytes: int
    estimated_tokens: int
    estimated_tokens_saved: int
    confidence_mix: dict[str, int]
    top_tools: tuple[str, ...]


class ToolUsageAnalyticsView(StrictModel):
    tool_name: str
    total_calls: int
    success_calls: int
    error_calls: int
    p50_duration_ms: int
    p95_duration_ms: int
    total_payload_bytes: int
    estimated_tokens: int
    estimated_tokens_saved: int
    confidence_mix: dict[str, int]


class InefficientToolCallView(StrictModel):
    kind: str
    tool_name: str | None = None
    session_id: str | None = None
    count: int
    description: str
    sample_event_ids: tuple[str, ...] = ()


class BenchmarkArtifactReferenceView(StrictModel):
    kind: str
    location: str
    description: str | None = None


class BenchmarkTaskResultView(StrictModel):
    task_id: str
    status: str
    tool_calls: int
    turn_count: int
    duration_ms: int
    session_id: str
    workspace_id: str | None = None
    repository_id: str | None = None
    repository_root: str
    first_high_value_tool: str | None = None
    first_high_value_tool_call_index: int | None = None
    used_high_value_tool_early: bool
    deterministic_action_kind: str | None = None
    deterministic_action_target_id: str | None = None
    deterministic_action_status: str
    provenance_confidence_mix: dict[str, int]
    provenance_source_kind_mix: dict[str, int]
    artifact_references: tuple[BenchmarkArtifactReferenceView, ...]
    notes: str | None = None


class BenchmarkReportView(StrictModel):
    schema_version: str
    report_id: str
    generated_at_utc: str
    adapter_name: str
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int
    avg_tool_calls: float
    avg_duration_ms: float
    high_value_tool_usage_rate: float
    high_value_tool_early_rate: float
    deterministic_action_success_rate: float
    authoritative_provenance_rate: float
    derived_provenance_rate: float
    heuristic_provenance_rate: float
    truth_coverage: TruthCoverageSummaryView | None = None
    tasks: tuple[BenchmarkTaskResultView, ...]
