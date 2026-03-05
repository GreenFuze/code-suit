from __future__ import annotations

from pydantic import field_validator, model_validator

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentContext, FileContext, SymbolContext
from suitcode.core.models import Component, Runner
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import ResolvedRelatedTest


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
        if self.target_kind == "file" and self.file_context is None:
            raise ValueError("file target requires file_context")
        if self.target_kind == "owner" and self.symbol_context is not None:
            raise ValueError("owner target must not include symbol_context")
        if self.target_kind == "owner" and self.file_context is not None:
            raise ValueError("owner target must not include file_context")
        if self.primary_component is not None and self.component_context is not None:
            if self.primary_component.id != self.component_context.component.id:
                raise ValueError("primary_component and component_context must reference the same component")
        return self
