from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry, SourceKind


class TruthCoverageDomain(StrEnum):
    __test__ = False
    ARCHITECTURE = "architecture"
    CODE = "code"
    TESTS = "tests"
    QUALITY = "quality"
    ACTIONS = "actions"


class TruthAvailability(StrEnum):
    __test__ = False
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class TruthActionCapability(StrEnum):
    __test__ = False
    TESTS = "tests"
    BUILDS = "builds"
    RUNNERS = "runners"


class TruthCoverageByDomain(StrictModel):
    domain: TruthCoverageDomain
    total_entities: int
    authoritative_count: int
    derived_count: int
    heuristic_count: int
    unavailable_count: int = 0
    availability: TruthAvailability
    degraded_reason: str | None = None
    source_kind_mix: dict[str, int] = Field(default_factory=dict)
    source_tool_mix: dict[str, int] = Field(default_factory=dict)
    execution_available: bool | None = None
    action_capabilities: dict[str, bool] = Field(default_factory=dict)

    @field_validator(
        "total_entities",
        "authoritative_count",
        "derived_count",
        "heuristic_count",
        "unavailable_count",
    )
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("coverage counts must be >= 0")
        return value

    @field_validator("degraded_reason")
    @classmethod
    def _validate_degraded_reason(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("degraded_reason must not be empty")
        return value

    @field_validator("source_kind_mix")
    @classmethod
    def _validate_source_kind_mix(cls, value: dict[str, int]) -> dict[str, int]:
        allowed = {item.value for item in SourceKind}
        for key, count in value.items():
            if key not in allowed:
                raise ValueError(f"unsupported source_kind mix key: `{key}`")
            if count < 0:
                raise ValueError("source_kind_mix counts must be >= 0")
        return value

    @field_validator("source_tool_mix")
    @classmethod
    def _validate_source_tool_mix(cls, value: dict[str, int]) -> dict[str, int]:
        for key, count in value.items():
            if not key.strip():
                raise ValueError("source_tool_mix keys must not be empty")
            if count < 0:
                raise ValueError("source_tool_mix counts must be >= 0")
        return value

    @field_validator("action_capabilities")
    @classmethod
    def _validate_action_capabilities(cls, value: dict[str, bool]) -> dict[str, bool]:
        allowed = {item.value for item in TruthActionCapability}
        for key in value:
            if key not in allowed:
                raise ValueError(f"unsupported action capability key: `{key}`")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "TruthCoverageByDomain":
        total = self.authoritative_count + self.derived_count + self.heuristic_count + self.unavailable_count
        if total != self.total_entities:
            raise ValueError("authoritative + derived + heuristic + unavailable must equal total_entities")
        if self.availability == TruthAvailability.DEGRADED and self.degraded_reason is None:
            raise ValueError("degraded availability requires degraded_reason")
        if self.availability == TruthAvailability.AVAILABLE and self.degraded_reason is not None:
            raise ValueError("available coverage must not include degraded_reason")
        if self.domain != TruthCoverageDomain.ACTIONS and self.action_capabilities:
            raise ValueError("action_capabilities are allowed only for the actions domain")
        if self.domain not in {TruthCoverageDomain.QUALITY, TruthCoverageDomain.ACTIONS} and self.execution_available is not None:
            raise ValueError("execution_available is allowed only for quality and actions domains")
        return self


class TruthCoverageSummary(StrictModel):
    scope_kind: str
    scope_id: str
    domains: tuple[TruthCoverageByDomain, ...]
    overall_authoritative_count: int
    overall_derived_count: int
    overall_heuristic_count: int
    overall_unavailable_count: int
    overall_availability: TruthAvailability
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("scope_kind", "scope_id")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> "TruthCoverageSummary":
        allowed_scope_kinds = {"repository", "change"}
        if self.scope_kind not in allowed_scope_kinds:
            raise ValueError(f"unsupported scope_kind: `{self.scope_kind}`")
        expected_domains = {item.value for item in TruthCoverageDomain}
        actual_domains = {item.domain.value for item in self.domains}
        if actual_domains != expected_domains or len(self.domains) != len(expected_domains):
            raise ValueError("domains must contain exactly one entry for each truth coverage domain")
        if self.overall_authoritative_count != sum(item.authoritative_count for item in self.domains):
            raise ValueError("overall_authoritative_count is inconsistent with domain counts")
        if self.overall_derived_count != sum(item.derived_count for item in self.domains):
            raise ValueError("overall_derived_count is inconsistent with domain counts")
        if self.overall_heuristic_count != sum(item.heuristic_count for item in self.domains):
            raise ValueError("overall_heuristic_count is inconsistent with domain counts")
        if self.overall_unavailable_count != sum(item.unavailable_count for item in self.domains):
            raise ValueError("overall_unavailable_count is inconsistent with domain counts")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self
