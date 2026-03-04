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


class AggregatorView(StrictModel):
    id: str
    name: str


class RunnerView(StrictModel):
    id: str
    name: str
    argv: tuple[str, ...]
    cwd: str | None = None


class PackageManagerView(StrictModel):
    id: str
    name: str
    manager: str
    lockfile_path: str | None = None


class ExternalPackageView(StrictModel):
    id: str
    name: str
    manager_id: str | None = None
    version_spec: str | None = None


class FileView(StrictModel):
    id: str
    path: str
    language: str | None = None
    owner_id: str


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


class LocationView(StrictModel):
    path: str
    line_start: int
    line_end: int | None = None
    column_start: int
    column_end: int | None = None
    symbol_id: str | None = None


class OwnerView(StrictModel):
    id: str
    kind: str
    name: str


class FileOwnerView(StrictModel):
    file: FileView
    owner: OwnerView


class TestDefinitionView(StrictModel):
    id: str
    name: str
    framework: str
    test_files: tuple[str, ...]
    discovery_method: str
    discovery_tool: str | None = None
    is_authoritative: bool


class RelatedTestView(StrictModel):
    id: str
    name: str
    framework: str
    test_files: tuple[str, ...]
    discovery_method: str
    discovery_tool: str | None = None
    is_authoritative: bool
    relation_reason: str
    matched_owner_id: str | None = None
    matched_path: str | None = None


class DependencyRefView(StrictModel):
    target_id: str
    target_kind: str
    dependency_scope: str


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


class FileContextView(StrictModel):
    file: FileView
    owner: OwnerView
    symbol_count: int
    symbols_preview: tuple[SymbolView, ...]
    related_test_count: int
    related_tests_preview: tuple[RelatedTestView, ...]
    quality_provider_ids: tuple[str, ...]


class SymbolContextView(StrictModel):
    symbol: SymbolView
    owner: OwnerView
    definition_count: int
    definitions: tuple[LocationView, ...]
    reference_count: int
    references_preview: tuple[LocationView, ...]
    related_test_count: int
    related_tests_preview: tuple[RelatedTestView, ...]


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


class QualityDiagnosticView(StrictModel):
    tool: str
    severity: str
    message: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    rule_id: str | None = None


class QualityEntityDeltaView(StrictModel):
    added: tuple[SymbolView, ...] = Field(default_factory=tuple)
    removed: tuple[SymbolView, ...] = Field(default_factory=tuple)
    updated: tuple[SymbolView, ...] = Field(default_factory=tuple)


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
