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
    test_files: tuple[str, ...]
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
    provenance: tuple[ProvenanceView, ...]
