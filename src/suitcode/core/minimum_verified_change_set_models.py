from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.action_models import RepositoryAction
from suitcode.core.build_models import BuildTargetDescription
from suitcode.core.models import Component
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import TestTargetDescription


class MinimumVerifiedItemKind(StrEnum):
    __test__ = False
    TEST_TARGET = "test_target"
    BUILD_TARGET = "build_target"
    RUNNER_ACTION = "runner_action"
    QUALITY_OPERATION = "quality_operation"


class MinimumVerifiedExclusionReason(StrEnum):
    __test__ = False
    DUPLICATE_REPLACED_BY_STRONGER_MATCH = "duplicate_replaced_by_stronger_match"
    BROAD_TEST_REPLACED_BY_SPECIFIC_TESTS = "broad_test_replaced_by_specific_tests"
    REPOSITORY_BUILD_REPLACED_BY_NARROWER_BUILD = "repository_build_replaced_by_narrower_build"
    RUNNER_NOT_DIRECTLY_VALIDATION_RELEVANT = "runner_not_directly_validation_relevant"
    DUPLICATE_QUALITY_OPERATION_COLLAPSED = "duplicate_quality_operation_collapsed"


class QualityOperationScope(StrEnum):
    __test__ = False
    VALIDATION = "validation"
    HYGIENE = "hygiene"


class QualityOperationKind(StrEnum):
    __test__ = False
    LINT = "lint"
    FORMAT = "format"


class MinimumVerifiedEvidenceEdgeKind(StrEnum):
    __test__ = False
    TARGET_TEST_TARGET = "target_test_target"
    COMPONENT_BUILD_TARGET = "component_build_target"
    OWNER_BUILD_TARGET = "owner_build_target"
    TARGET_RUNNER_ACTION = "target_runner_action"
    TARGET_QUALITY_VALIDATION = "target_quality_validation"
    TARGET_QUALITY_HYGIENE = "target_quality_hygiene"


class MinimumVerifiedEvidenceEdge(StrictModel):
    source_node_kind: str
    source_node_id: str
    target_node_kind: str
    target_node_id: str
    edge_kind: MinimumVerifiedEvidenceEdgeKind
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
    def _validate_provenance(self) -> "MinimumVerifiedEvidenceEdge":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class MinimumVerifiedTestTarget(StrictModel):
    target: TestTargetDescription
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("inclusion_reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("inclusion_reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "MinimumVerifiedTestTarget":
        if not self.proof_edges:
            raise ValueError("proof_edges must not be empty")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class MinimumVerifiedBuildTarget(StrictModel):
    target: BuildTargetDescription
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("inclusion_reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("inclusion_reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "MinimumVerifiedBuildTarget":
        if not self.proof_edges:
            raise ValueError("proof_edges must not be empty")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class MinimumVerifiedRunnerAction(StrictModel):
    action: RepositoryAction
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("inclusion_reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("inclusion_reason must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "MinimumVerifiedRunnerAction":
        if self.action.kind.value != "runner_execution":
            raise ValueError("runner action must use kind `runner_execution`")
        if not self.proof_edges:
            raise ValueError("proof_edges must not be empty")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class MinimumVerifiedQualityOperation(StrictModel):
    id: str
    provider_id: str
    operation: QualityOperationKind
    scope: QualityOperationScope
    repository_rel_paths: tuple[str, ...]
    mcp_tool_name: str
    is_fix: bool | None = None
    is_mutating: bool
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("id", "provider_id", "mcp_tool_name", "inclusion_reason")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @field_validator("repository_rel_paths")
    @classmethod
    def _validate_repository_rel_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("repository_rel_paths must not be empty")
        normalized: list[str] = []
        for item in value:
            normalized_item = normalize_repository_relative_path(item)
            if normalized_item in normalized:
                raise ValueError("repository_rel_paths must not contain duplicates")
            normalized.append(normalized_item)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_shape(self) -> "MinimumVerifiedQualityOperation":
        if not self.proof_edges:
            raise ValueError("proof_edges must not be empty")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if self.operation == QualityOperationKind.LINT:
            if self.scope != QualityOperationScope.VALIDATION:
                raise ValueError("lint operations must use validation scope")
            if self.mcp_tool_name != "lint_file":
                raise ValueError("lint operations must use `lint_file`")
            if self.is_fix is not False:
                raise ValueError("lint validation operations must use is_fix=False")
            if self.is_mutating:
                raise ValueError("lint validation operations must not mutate content")
        else:
            if self.scope != QualityOperationScope.HYGIENE:
                raise ValueError("format operations must use hygiene scope")
            if self.mcp_tool_name != "format_file":
                raise ValueError("format operations must use `format_file`")
            if self.is_fix is not None:
                raise ValueError("format operations must not define is_fix")
            if not self.is_mutating:
                raise ValueError("format operations must be marked mutating")
        return self


class ExcludedMinimumVerifiedItem(StrictModel):
    item_kind: MinimumVerifiedItemKind
    item_id: str
    reason_code: MinimumVerifiedExclusionReason
    reason: str
    replaced_by_ids: tuple[str, ...] = ()
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("item_id", "reason")
    @classmethod
    def _validate_non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @field_validator("replaced_by_ids")
    @classmethod
    def _validate_replaced_by_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            if not item.strip():
                raise ValueError("replaced_by_ids must not contain empty values")
            if item in normalized:
                raise ValueError("replaced_by_ids must not contain duplicates")
            normalized.append(item)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_provenance(self) -> "ExcludedMinimumVerifiedItem":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class MinimumVerifiedChangeSet(StrictModel):
    target_kind: str
    owner: OwnedNodeInfo
    primary_component: Component | None = None
    tests: tuple[MinimumVerifiedTestTarget, ...]
    build_targets: tuple[MinimumVerifiedBuildTarget, ...]
    runner_actions: tuple[MinimumVerifiedRunnerAction, ...]
    quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...]
    quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...]
    excluded_items: tuple[ExcludedMinimumVerifiedItem, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("target_kind")
    @classmethod
    def _validate_target_kind(cls, value: str) -> str:
        allowed = {"symbol", "file", "owner"}
        if value not in allowed:
            raise ValueError(f"unsupported target_kind: `{value}`")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "MinimumVerifiedChangeSet":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if not any(
            (
                self.tests,
                self.build_targets,
                self.runner_actions,
                self.quality_validation_operations,
                self.quality_hygiene_operations,
            )
        ):
            raise ValueError(
                "minimum verified change set requires at least one deterministic validation or hygiene surface"
            )
        return self
