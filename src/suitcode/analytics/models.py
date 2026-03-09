from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from suitcode.core.truth_coverage_models import TruthCoverageSummary


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
    benchmark_run_id: str | None = None
    benchmark_task_id: str | None = None
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

    @field_validator(
        "event_id",
        "session_id",
        "tool_name",
        "arguments_fingerprint_sha256",
        "benchmark_run_id",
        "benchmark_task_id",
    )
    @classmethod
    def _validate_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
        if (self.benchmark_run_id is None) != (self.benchmark_task_id is None):
            raise ValueError("benchmark_run_id and benchmark_task_id must be provided together")
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


class BenchmarkArtifactReference(StrictModel):
    kind: str
    location: str
    description: str | None = None

    @field_validator("kind", "location")
    @classmethod
    def _validate_benchmark_artifact_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()


class BenchmarkTaskResult(StrictModel):
    task_id: str
    status: str
    tool_calls: int
    turn_count: int
    duration_ms: int
    session_id: str
    workspace_id: str | None = None
    repository_id: str | None = None
    repository_root: str
    first_high_value_tool: str | None = None
    first_high_value_tool_call_index: int | None = None
    used_high_value_tool_early: bool = False
    deterministic_action_kind: str | None = None
    deterministic_action_target_id: str | None = None
    deterministic_action_status: str = "not_applicable"
    provenance_confidence_mix: dict[str, int] = Field(default_factory=dict)
    provenance_source_kind_mix: dict[str, int] = Field(default_factory=dict)
    artifact_references: tuple[BenchmarkArtifactReference, ...] = ()
    notes: str | None = None

    @field_validator("task_id", "status", "session_id", "repository_root")
    @classmethod
    def _validate_benchmark_task_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_benchmark_task_result(self) -> "BenchmarkTaskResult":
        if self.tool_calls < 0 or self.turn_count < 0 or self.duration_ms < 0:
            raise ValueError("tool_calls, turn_count, and duration_ms must be >= 0")
        if self.first_high_value_tool_call_index is not None and self.first_high_value_tool_call_index <= 0:
            raise ValueError("first_high_value_tool_call_index must be > 0 when provided")
        if self.used_high_value_tool_early and self.first_high_value_tool_call_index is None:
            raise ValueError("used_high_value_tool_early requires first_high_value_tool_call_index")
        if self.first_high_value_tool is None and self.first_high_value_tool_call_index is not None:
            raise ValueError("first_high_value_tool_call_index requires first_high_value_tool")
        if self.deterministic_action_status not in {"not_applicable", "passed", "failed", "error"}:
            raise ValueError("deterministic_action_status is invalid")
        if (self.deterministic_action_kind is None) != (self.deterministic_action_target_id is None):
            raise ValueError("deterministic_action_kind and deterministic_action_target_id must be provided together")
        return self


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
    high_value_tool_usage_rate: float
    high_value_tool_early_rate: float
    deterministic_action_success_rate: float
    authoritative_provenance_rate: float
    derived_provenance_rate: float
    heuristic_provenance_rate: float
    truth_coverage: TruthCoverageSummary | None = None
    tasks: tuple[BenchmarkTaskResult, ...]

    @field_validator("report_id", "generated_at_utc", "adapter_name")
    @classmethod
    def _validate_benchmark_report_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()
