from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry, SourceKind


class RuntimeCapabilityAvailability(StrEnum):
    __test__ = False
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class RuntimeCapability(StrictModel):
    capability_id: str
    availability: RuntimeCapabilityAvailability
    source_kind: SourceKind
    source_tool: str | None = None
    reason: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("capability_id")
    @classmethod
    def _validate_capability_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capability_id must not be empty")
        return value.strip()

    @field_validator("source_tool", "reason")
    @classmethod
    def _validate_optional_string(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional runtime capability values must not be empty")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _validate_shape(self) -> "RuntimeCapability":
        if self.availability != RuntimeCapabilityAvailability.AVAILABLE and self.reason is None:
            raise ValueError("degraded/unavailable runtime capability requires reason")
        if not self.provenance:
            raise ValueError("runtime capability provenance must not be empty")
        return self


class CodeRuntimeCapabilities(StrictModel):
    symbol_search: RuntimeCapability
    symbols_in_file: RuntimeCapability
    definitions: RuntimeCapability
    references: RuntimeCapability


class QualityRuntimeCapabilities(StrictModel):
    lint: RuntimeCapability
    format: RuntimeCapability


class TestRuntimeCapabilities(StrictModel):
    discovery: RuntimeCapability
    execution: RuntimeCapability


class ActionRuntimeCapabilities(StrictModel):
    tests: RuntimeCapability
    builds: RuntimeCapability
    runners: RuntimeCapability
