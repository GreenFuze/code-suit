from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyticsStatus(StrEnum):
    __test__ = False
    SUCCESS = "success"
    ERROR = "error"


class SavingsConfidence(StrEnum):
    __test__ = False
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalyticsEvent(StrictModel):
    schema_version: str = "1.0"
    event_id: str
    session_id: str
    timestamp_utc: str
    tool_name: str
    workspace_id: str | None = None
    repository_id: str | None = None
    repository_root: str | None = None
    arguments_redacted: dict[str, object] = Field(default_factory=dict)
    arguments_fingerprint_sha256: str
    status: AnalyticsStatus
    error_class: str | None = None
    error_message: str | None = None
    duration_ms: int
    output_model_type: str | None = None
    output_payload_bytes: int | None = None
    output_payload_sha256: str | None = None
    output_item_count: int | None = None

    @field_validator("event_id", "session_id", "tool_name", "arguments_fingerprint_sha256")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("timestamp_utc")
    @classmethod
    def _validate_timestamp_utc(cls, value: str) -> str:
        if not value.endswith("Z"):
            raise ValueError("timestamp_utc must be UTC ISO-8601 with Z suffix")
        candidate = value[:-1] + "+00:00"
        datetime.fromisoformat(candidate)
        return value

    @model_validator(mode="after")
    def _validate_status_fields(self) -> "AnalyticsEvent":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.status == AnalyticsStatus.SUCCESS:
            if self.error_class is not None or self.error_message is not None:
                raise ValueError("success events must not include error fields")
        if self.status == AnalyticsStatus.ERROR:
            if not self.error_class:
                raise ValueError("error events must include error_class")
        return self


class TokenEstimate(StrictModel):
    tool_name: str
    actual_tokens_estimate: int
    counterfactual_tokens_estimate: int
    estimated_tokens_saved: int
    confidence_level: SavingsConfidence


class ToolUsageStats(StrictModel):
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


class AnalyticsSummary(StrictModel):
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


class InefficiencyFinding(StrictModel):
    kind: str
    tool_name: str | None = None
    session_id: str | None = None
    count: int
    description: str
    sample_event_ids: tuple[str, ...] = ()


class BenchmarkTaskResult(StrictModel):
    task_id: str
    status: str
    tool_calls: int
    duration_ms: int
    notes: str | None = None


class BenchmarkReport(StrictModel):
    schema_version: str = "1.0"
    report_id: str
    generated_at_utc: str
    adapter_name: str
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int
    avg_tool_calls: float
    avg_duration_ms: float
    tasks: tuple[BenchmarkTaskResult, ...]
