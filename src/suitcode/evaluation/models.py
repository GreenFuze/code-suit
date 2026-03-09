from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel
from suitcode.analytics.transcript_models import TranscriptTokenBreakdown


class EvaluationStatus(StrEnum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class EvaluationFailureKind(StrEnum):
    __test__ = False
    TIMEOUT = "timeout"
    CLI_ERROR = "cli_error"
    USAGE_LIMIT = "usage_limit"
    SESSION_ARTIFACT_MISSING = "session_artifact_missing"
    SESSION_CORRELATION_AMBIGUOUS = "session_correlation_ambiguous"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    REQUIRED_TOOLS_MISSING = "required_tools_missing"
    ARGUMENT_MISMATCH = "argument_mismatch"
    ANSWER_MISMATCH = "answer_mismatch"
    REQUIRED_ACTION_NOT_EXECUTED = "required_action_not_executed"
    REQUIRED_ACTION_WRONG_TARGET = "required_action_wrong_target"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


class ToolSelectionScore(StrictModel):
    required_tools_present: bool
    required_tool_names: tuple[str, ...]
    used_tool_names: tuple[str, ...]
    missing_required_tools: tuple[str, ...] = ()
    unexpected_blocking_tools: tuple[str, ...] = ()
    first_suitcode_tool: str | None = None
    first_high_value_tool: str | None = None
    first_high_value_tool_index: int | None = None
    used_high_value_tool_early: bool = False


class ArgumentScore(StrictModel):
    tool_name: str
    expected_argument_subset: dict[str, object] = Field(default_factory=dict)
    matched: bool
    mismatches: tuple[str, ...] = ()

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name must not be empty")
        return value.strip()


class AnswerScore(StrictModel):
    schema_valid: bool
    field_matches: dict[str, bool] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()
    mismatched_fields: tuple[str, ...] = ()


class ActionScore(StrictModel):
    required_action_kind: str | None = None
    required_action_target_id: str | None = None
    executed: bool
    matched_target: bool
    status: str | None = None


class RequiredToolTrace(StrictModel):
    tool_name: str
    attempt_number: int = 1
    call_index: int | None = None
    called: bool
    success: bool
    error_excerpt: str | None = None
    correlated_duration_ms: int | None = None
    timed_out: bool = False
    arguments_excerpt: str | None = None

    @field_validator("tool_name", "error_excerpt", "arguments_excerpt")
    @classmethod
    def _validate_trace_string(cls, value: str | None):
        if value is None:
            return None
        if not value.strip():
            raise ValueError("required tool trace strings must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_trace(self) -> "RequiredToolTrace":
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")
        if self.call_index is not None and self.call_index <= 0:
            raise ValueError("call_index must be > 0 when provided")
        if not self.called and self.success:
            raise ValueError("uncalled required tool traces must not be marked successful")
        if self.correlated_duration_ms is not None and self.correlated_duration_ms < 0:
            raise ValueError("correlated_duration_ms must be >= 0")
        if self.timed_out and self.success:
            raise ValueError("timed_out required tool traces must not be marked successful")
        return self


class CodexEvaluationTaskResult(StrictModel):
    task_id: str
    task_family: str
    status: EvaluationStatus
    failure_kind: EvaluationFailureKind | None = None
    failure_summary: str | None = None
    session_id: str | None = None
    repository_root: str
    duration_ms: int
    attempt_count: int = 1
    attempt_failure_kinds: tuple[str, ...] = ()
    infrastructure_retry_applied: bool = False
    turn_count: int | None = None
    required_tool_count: int = 0
    used_suitcode_tool_count: int | None = None
    used_high_value_tool_count: int | None = None
    first_suitcode_tool_index: int | None = None
    first_high_value_tool_index: int | None = None
    tool_selection: ToolSelectionScore
    argument_scores: tuple[ArgumentScore, ...] = ()
    answer_score: AnswerScore
    action_score: ActionScore
    required_tool_traces: tuple[RequiredToolTrace, ...] = ()
    transcript_token_breakdown: TranscriptTokenBreakdown | None = None
    correlation_quality: str | None = None
    stdout_jsonl_path: str
    rollout_artifact_path: str | None = None
    output_last_message_path: str
    notes: tuple[str, ...] = ()

    @field_validator("task_id", "task_family", "repository_root", "stdout_jsonl_path", "output_last_message_path")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_result(self) -> "CodexEvaluationTaskResult":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.attempt_count <= 0:
            raise ValueError("attempt_count must be > 0")
        if self.turn_count is not None and self.turn_count < 0:
            raise ValueError("turn_count must be >= 0")
        if self.required_tool_count < 0:
            raise ValueError("required_tool_count must be >= 0")
        if self.used_suitcode_tool_count is not None and self.used_suitcode_tool_count < 0:
            raise ValueError("used_suitcode_tool_count must be >= 0")
        if self.used_high_value_tool_count is not None and self.used_high_value_tool_count < 0:
            raise ValueError("used_high_value_tool_count must be >= 0")
        if self.first_suitcode_tool_index is not None and self.first_suitcode_tool_index <= 0:
            raise ValueError("first_suitcode_tool_index must be > 0")
        if self.first_high_value_tool_index is not None and self.first_high_value_tool_index <= 0:
            raise ValueError("first_high_value_tool_index must be > 0")
        if self.status == EvaluationStatus.PASSED:
            if self.failure_kind is not None or self.failure_summary is not None:
                raise ValueError("passed results must not carry failure information")
        else:
            if self.failure_kind is None or self.failure_summary is None or not self.failure_summary.strip():
                raise ValueError("failed/error results must include failure_kind and failure_summary")
        if self.attempt_failure_kinds and self.attempt_count <= 1:
            raise ValueError("attempt_failure_kinds require attempt_count > 1")
        if self.infrastructure_retry_applied and self.attempt_count <= 1:
            raise ValueError("infrastructure_retry_applied requires attempt_count > 1")
        return self


class CodexEvaluationReport(StrictModel):
    report_id: str
    generated_at_utc: str
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int
    avg_duration_ms: float
    avg_transcript_tokens: float | None = None
    avg_tokens_before_first_suitcode_tool: float | None = None
    avg_tokens_before_first_high_value_tool: float | None = None
    required_tool_success_rate: float
    high_value_tool_early_rate: float
    answer_schema_success_rate: float
    deterministic_action_success_rate: float
    timeout_rate: float = 0.0
    session_artifact_resolution_rate: float = 0.0
    retry_rate: float = 0.0
    retried_task_count: int = 0
    post_retry_pass_count: int = 0
    avg_first_suitcode_tool_index: float | None = None
    avg_first_high_value_tool_index: float | None = None
    sessions_with_no_high_value_tool_rate: float = 0.0
    failure_kind_mix: dict[str, int] = Field(default_factory=dict)
    infrastructure_failure_kind_mix: dict[str, int] = Field(default_factory=dict)
    required_tool_timeout_mix: dict[str, int] = Field(default_factory=dict)
    required_tool_failure_mix: dict[str, int] = Field(default_factory=dict)
    correlation_quality_mix: dict[str, int] = Field(default_factory=dict)
    tasks: tuple[CodexEvaluationTaskResult, ...]

    @field_validator("report_id", "generated_at_utc")
    @classmethod
    def _validate_report_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_report(self) -> "CodexEvaluationReport":
        if any(value < 0 for value in (self.task_total, self.task_passed, self.task_failed, self.task_error)):
            raise ValueError("report counts must be >= 0")
        if self.task_passed + self.task_failed + self.task_error != self.task_total:
            raise ValueError("report counts are inconsistent")
        return self
