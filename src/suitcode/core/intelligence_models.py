from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import Component, EntityInfo, FileInfo
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import ResolvedRelatedTest


class DependencyRef(StrictModel):
    target_id: str
    target_kind: str
    dependency_scope: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("target_id")
    @classmethod
    def _validate_target_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target_id must not be empty")
        return value

    @field_validator("target_kind")
    @classmethod
    def _validate_target_kind(cls, value: str) -> str:
        allowed = {"component", "external_package"}
        if value not in allowed:
            raise ValueError(f"unsupported target_kind: `{value}`")
        return value

    @field_validator("dependency_scope")
    @classmethod
    def _validate_dependency_scope(cls, value: str) -> str:
        allowed = {"runtime", "dev", "peer", "optional", "declared", "test"}
        if value not in allowed:
            raise ValueError(f"unsupported dependency_scope: `{value}`")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "DependencyRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.LSP for item in self.provenance):
            raise ValueError("dependency provenance must not use LSP source_kind")
        return self


class ComponentDependencyEdge(StrictModel):
    source_component_id: str
    target_id: str
    target_kind: str
    dependency_scope: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("source_component_id")
    @classmethod
    def _validate_source_component_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_component_id must not be empty")
        return value

    @field_validator("target_id")
    @classmethod
    def _validate_target_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target_id must not be empty")
        return value

    @field_validator("target_kind")
    @classmethod
    def _validate_target_kind(cls, value: str) -> str:
        allowed = {"component", "external_package"}
        if value not in allowed:
            raise ValueError(f"unsupported target_kind: `{value}`")
        return value

    @field_validator("dependency_scope")
    @classmethod
    def _validate_dependency_scope(cls, value: str) -> str:
        allowed = {"runtime", "dev", "peer", "optional", "declared", "test"}
        if value not in allowed:
            raise ValueError(f"unsupported dependency_scope: `{value}`")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ComponentDependencyEdge":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.LSP for item in self.provenance):
            raise ValueError("dependency provenance must not use LSP source_kind")
        return self


class ComponentContext(StrictModel):
    component: Component
    owned_file_count: int
    owned_files_preview: tuple[FileInfo, ...]
    runner_ids: tuple[str, ...]
    related_test_ids: tuple[str, ...]
    dependency_count: int
    dependencies_preview: tuple[DependencyRef, ...]
    dependent_count: int
    dependents_preview: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ComponentContext":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class FileRelationshipKind(StrEnum):
    __test__ = False
    IMPORTS = "imports"
    IMPORTED_BY = "imported_by"


class FileRelationshipRef(StrictModel):
    repository_rel_path: str
    relationship_kind: FileRelationshipKind
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path")
    @classmethod
    def _validate_repository_rel_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repository_rel_path must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "FileRelationshipRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("file relationship provenance must not be heuristic")
        return self


class RenderEdgeKind(StrEnum):
    __test__ = False
    RENDERS = "renders"
    RENDERED_BY = "rendered_by"


class RenderEdgeRef(StrictModel):
    repository_rel_path: str
    relationship_kind: RenderEdgeKind
    line_start: int
    column_start: int
    prop_names: tuple[str, ...]
    has_spread_props: bool
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path")
    @classmethod
    def _validate_repository_rel_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("repository_rel_path must not be empty")
        return value

    @field_validator("line_start", "column_start")
    @classmethod
    def _validate_position(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value

    @field_validator("prop_names")
    @classmethod
    def _validate_prop_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            candidate = item.strip()
            if not candidate:
                raise ValueError("prop_names must not contain empty values")
            if candidate in normalized:
                raise ValueError("prop_names must not contain duplicates")
            normalized.append(candidate)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_provenance(self) -> "RenderEdgeRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("render edge provenance must not be heuristic")
        return self


class StaticAnalysisSiteRef(StrictModel):
    repository_rel_path: str
    line_start: int
    column_start: int
    label: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path", "label")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("line_start", "column_start")
    @classmethod
    def _validate_position(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "StaticAnalysisSiteRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("static analysis site provenance must not be heuristic")
        return self


class InvariantFindingKind(StrEnum):
    __test__ = False
    MAYBE_MISSING_FIELD_ACCESS = "maybe_missing_field_access"


class InvariantAccessKind(StrEnum):
    __test__ = False
    PROPERTY_READ = "property_read"
    METHOD_CALL = "method_call"


class InvariantFindingRef(StrictModel):
    repository_rel_path: str
    finding_kind: InvariantFindingKind
    access_kind: InvariantAccessKind
    line_start: int
    column_start: int
    field_name: str
    subject_label: str
    declared_type: str | None = None
    producer_site_count: int
    producer_sites_preview: tuple[StaticAnalysisSiteRef, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path", "field_name", "subject_label")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("line_start", "column_start", "producer_site_count")
    @classmethod
    def _validate_non_negative(cls, value: int, info) -> int:
        minimum = 0 if info.field_name == "producer_site_count" else 1
        if value < minimum:
            raise ValueError(f"{info.field_name} must be >= {minimum}")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "InvariantFindingRef":
        if self.producer_site_count != len(self.producer_sites_preview):
            raise ValueError("producer_site_count must match producer_sites_preview length")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("invariant finding provenance must not be heuristic")
        return self


class StaticFlowEdgeKind(StrEnum):
    __test__ = False
    CALLS_LOCAL_SYMBOL = "calls_local_symbol"
    PRODUCES_VALUE_FOR = "produces_value_for"


class StaticFlowEdgeRef(StrictModel):
    repository_rel_path: str
    edge_kind: StaticFlowEdgeKind
    line_start: int
    column_start: int
    source_label: str
    target_label: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path", "source_label", "target_label")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("line_start", "column_start")
    @classmethod
    def _validate_position(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "StaticFlowEdgeRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("static flow provenance must not be heuristic")
        return self


class ImplementationFlowStepKind(StrEnum):
    __test__ = False
    SYMBOL_ANCHOR = "symbol_anchor"
    EXTERNAL_REFERENCE_ANCHOR = "external_reference_anchor"
    TEST_SEAM = "test_seam"
    STATE_SITE = "state_site"
    PROP_EDGE = "prop_edge"
    RENDER_EDGE = "render_edge"
    LOCAL_FLOW_EDGE = "local_flow_edge"
    EVENT_SUBSCRIBE = "event_subscribe"
    EVENT_PUBLISH = "event_publish"
    API_CALL = "api_call"
    CONTRACT_USE = "contract_use"
    IMPLEMENTATION_ANCHOR = "implementation_anchor"
    RELATED_TEST_ANCHOR = "related_test_anchor"


class ImplementationFlowStepRef(StrictModel):
    repository_rel_path: str
    line_start: int
    column_start: int
    step_kind: ImplementationFlowStepKind
    source_label: str
    target_label: str | None = None
    detail_label: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("repository_rel_path", "source_label")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("target_label", "detail_label")
    @classmethod
    def _validate_optional_text(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value.strip()

    @field_validator("line_start", "column_start")
    @classmethod
    def _validate_position(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ImplementationFlowStepRef":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("implementation flow provenance must not be heuristic")
        return self


class ImplementationFlowSummaryRef(StrictModel):
    step_count: int
    steps_preview: tuple[ImplementationFlowStepRef, ...]
    provider_ids: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("step_count")
    @classmethod
    def _validate_step_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_count must be >= 1")
        return value

    @field_validator("provider_ids")
    @classmethod
    def _validate_provider_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("provider_ids must not contain empty values")
        if len(set(value)) != len(value):
            raise ValueError("provider_ids must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _validate_summary(self) -> "ImplementationFlowSummaryRef":
        if not self.steps_preview:
            raise ValueError("steps_preview must not be empty")
        if self.step_count < len(self.steps_preview):
            raise ValueError("step_count must be >= len(steps_preview)")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if any(item.source_kind == SourceKind.HEURISTIC for item in self.provenance):
            raise ValueError("implementation flow summary provenance must not be heuristic")
        return self


class FileContext(StrictModel):
    file_info: FileInfo
    owner: OwnedNodeInfo
    symbol_count: int
    symbols_preview: tuple[EntityInfo, ...]
    reference_site_count: int
    reference_sites_preview: tuple[CodeLocation, ...]
    dependency_file_count: int
    dependency_files_preview: tuple[FileRelationshipRef, ...]
    dependent_file_count: int
    dependent_files_preview: tuple[FileRelationshipRef, ...]
    render_child_count: int
    render_children_preview: tuple[RenderEdgeRef, ...]
    render_parent_count: int
    render_parents_preview: tuple[RenderEdgeRef, ...]
    invariant_finding_count: int
    invariant_findings_preview: tuple[InvariantFindingRef, ...]
    local_flow_edge_count: int
    local_flow_edges_preview: tuple[StaticFlowEdgeRef, ...]
    implementation_location_count: int
    implementation_locations_preview: tuple[CodeLocation, ...]
    related_test_count: int
    related_tests_preview: tuple[ResolvedRelatedTest, ...]
    quality_provider_ids: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "FileContext":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if (self.symbol_count > 0 or self.reference_site_count > 0 or self.implementation_location_count > 0) and not any(
            item.source_kind == SourceKind.LSP for item in self.provenance
        ):
            raise ValueError("file contexts with symbol, reference, or implementation evidence must include LSP provenance")
        return self


class SymbolContext(StrictModel):
    symbol: EntityInfo
    owner: OwnedNodeInfo
    definition_count: int
    definitions: tuple[CodeLocation, ...]
    reference_count: int
    references_preview: tuple[CodeLocation, ...]
    related_test_count: int
    related_tests_preview: tuple[ResolvedRelatedTest, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "SymbolContext":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if (self.definition_count > 0 or self.reference_count > 0) and not any(
            item.source_kind == SourceKind.LSP for item in self.provenance
        ):
            raise ValueError("symbol contexts with definitions or references must include LSP provenance")
        return self


class SymbolLookupHit(StrictModel):
    symbol: EntityInfo
    owner: OwnedNodeInfo | None = None
    reference_count: int
    reference_preview: tuple[CodeLocation, ...]
    related_tests_preview: tuple[ResolvedRelatedTest, ...]
    definition_anchor: CodeLocation | None = None
    context_source: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("context_source")
    @classmethod
    def _validate_context_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("context_source must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_symbol_lookup_hit(self) -> "SymbolLookupHit":
        if self.reference_count < 0:
            raise ValueError("reference_count must be >= 0")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if (
            self.reference_count > 0 or self.definition_anchor is not None
        ) and not any(item.source_kind == SourceKind.LSP for item in self.provenance):
            raise ValueError("symbol lookup hits with definitions or references must include LSP provenance")
        return self


class ImpactTarget(StrictModel):
    symbol_id: str | None = None
    repository_rel_path: str | None = None
    owner_id: str | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "ImpactTarget":
        populated = [
            self.symbol_id is not None,
            self.repository_rel_path is not None,
            self.owner_id is not None,
        ]
        if sum(populated) != 1:
            raise ValueError("exactly one of symbol_id, repository_rel_path, or owner_id must be provided")
        if self.symbol_id is not None and not self.symbol_id.strip():
            raise ValueError("symbol_id must not be empty")
        if self.repository_rel_path is not None and not self.repository_rel_path.strip():
            raise ValueError("repository_rel_path must not be empty")
        if self.owner_id is not None and not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        return self


class ImpactSummary(StrictModel):
    target_kind: str
    owner: OwnedNodeInfo
    primary_component_id: str | None = None
    dependent_component_count: int
    dependent_component_ids_preview: tuple[str, ...]
    reference_count: int
    references_preview: tuple[CodeLocation, ...]
    related_test_count: int
    related_test_ids_preview: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("target_kind")
    @classmethod
    def _validate_target_kind(cls, value: str) -> str:
        allowed = {"symbol", "file", "owner"}
        if value not in allowed:
            raise ValueError(f"unsupported target_kind: `{value}`")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ImpactSummary":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self
