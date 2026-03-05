from __future__ import annotations

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


class FileContext(StrictModel):
    file_info: FileInfo
    owner: OwnedNodeInfo
    symbol_count: int
    symbols_preview: tuple[EntityInfo, ...]
    related_test_count: int
    related_tests_preview: tuple[ResolvedRelatedTest, ...]
    quality_provider_ids: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "FileContext":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if self.symbol_count > 0 and not any(item.source_kind == SourceKind.LSP for item in self.provenance):
            raise ValueError("file contexts with symbols must include LSP provenance")
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
