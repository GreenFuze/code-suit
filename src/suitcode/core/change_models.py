from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentContext, FileContext, SymbolContext
from suitcode.core.models import Component, Runner
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import ResolvedRelatedTest
from suitcode.core.truth_coverage_models import TruthCoverageSummary


class ChangeTarget(StrictModel):
    symbol_id: str | None = None
    repository_rel_path: str | None = None
    owner_id: str | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "ChangeTarget":
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


class QualityGateInfo(StrictModel):
    provider_id: str
    provider_roles: tuple[str, ...]
    applies: bool
    reason: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("provider_id", "reason")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "QualityGateInfo":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class RunnerImpact(StrictModel):
    runner: Runner
    reason: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "RunnerImpact":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class TestImpact(StrictModel):
    related_test: ResolvedRelatedTest
    reason: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "TestImpact":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class ChangeEvidenceEdgeKind(StrEnum):
    __test__ = False
    TARGET_OWNER = "target_owner"
    OWNER_PRIMARY_COMPONENT = "owner_primary_component"
    TARGET_REFERENCE = "target_reference"
    COMPONENT_DEPENDENT_COMPONENT = "component_dependent_component"
    TARGET_RELATED_TEST = "target_related_test"
    TARGET_RELATED_RUNNER = "target_related_runner"
    TARGET_QUALITY_GATE = "target_quality_gate"


class ChangeEvidenceEdge(StrictModel):
    source_node_kind: str
    source_node_id: str
    target_node_kind: str
    target_node_id: str
    edge_kind: ChangeEvidenceEdgeKind
    reason: str
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator(
        "source_node_kind",
        "source_node_id",
        "target_node_kind",
        "target_node_id",
        "reason",
    )
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ChangeEvidenceEdge":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class ChangeEvidencePreview(StrictModel):
    total_edges: int
    counts_by_kind: dict[str, int]
    edges_preview: tuple[ChangeEvidenceEdge, ...]
    truncated: bool

    @field_validator("total_edges")
    @classmethod
    def _validate_total_edges(cls, value: int) -> int:
        if value < 1:
            raise ValueError("total_edges must be >= 1")
        return value

    @field_validator("counts_by_kind")
    @classmethod
    def _validate_counts_by_kind(cls, value: dict[str, int]) -> dict[str, int]:
        if not value:
            raise ValueError("counts_by_kind must not be empty")
        allowed = {item.value for item in ChangeEvidenceEdgeKind}
        normalized: dict[str, int] = {}
        for key, count in value.items():
            if key not in allowed:
                raise ValueError(f"unsupported evidence edge kind: `{key}`")
            if count < 0:
                raise ValueError("counts_by_kind values must be >= 0")
            normalized[key] = count
        return normalized

    @model_validator(mode="after")
    def _validate_preview(self) -> "ChangeEvidencePreview":
        if not self.edges_preview:
            raise ValueError("edges_preview must not be empty")
        counted = sum(self.counts_by_kind.values())
        if counted != self.total_edges:
            raise ValueError("sum(counts_by_kind.values()) must equal total_edges")
        if self.truncated and len(self.edges_preview) >= self.total_edges:
            raise ValueError("truncated previews must contain fewer edges than total_edges")
        if not self.truncated and len(self.edges_preview) != self.total_edges:
            raise ValueError("non-truncated previews must contain exactly total_edges entries")
        if len(self.edges_preview) > self.total_edges:
            raise ValueError("edges_preview must not exceed total_edges")
        return self


class ChangeImpact(StrictModel):
    target_kind: str
    owner: OwnedNodeInfo
    primary_component: Component | None = None
    component_context: ComponentContext | None = None
    file_context: FileContext | None = None
    symbol_context: SymbolContext | None = None
    dependent_components: tuple[Component, ...]
    reference_locations: tuple[CodeLocation, ...]
    related_tests: tuple[TestImpact, ...]
    related_runners: tuple[RunnerImpact, ...]
    quality_gates: tuple[QualityGateInfo, ...]
    evidence: ChangeEvidencePreview
    truth_coverage: TruthCoverageSummary
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("target_kind")
    @classmethod
    def _validate_target_kind(cls, value: str) -> str:
        allowed = {"symbol", "file", "owner"}
        if value not in allowed:
            raise ValueError(f"unsupported target_kind: `{value}`")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "ChangeImpact":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if self.target_kind == "symbol" and self.symbol_context is None:
            raise ValueError("symbol target requires symbol_context")
        if self.target_kind == "owner" and self.symbol_context is not None:
            raise ValueError("owner target must not include symbol_context")
        if self.target_kind == "owner" and self.file_context is not None:
            raise ValueError("owner target must not include file_context")
        if self.primary_component is not None and self.component_context is not None:
            if self.primary_component.id != self.component_context.component.id:
                raise ValueError("primary_component and component_context must reference the same component")
        return self
