from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel
from suitcode.analytics.transcript_models import TranscriptCapture, TranscriptTokenBreakdown


class NativeAgentKind(StrEnum):
    __test__ = False
    CODEX = "codex"


class CorrelationQuality(StrEnum):
    __test__ = False
    NONE = "none"
    REPO_ONLY = "repo_only"
    SESSION_ONLY = "session_only"
    TOOL_OVERLAP = "tool_overlap"
    STRONG = "strong"


class CodexSessionArtifact(StrictModel):
    session_id: str
    artifact_path: str
    repository_root: str | None = None
    started_at: datetime
    last_event_at: datetime
    cwd: str | None = None
    cli_version: str | None = None
    model_provider: str | None = None
    event_count: int

    @field_validator("session_id", "artifact_path")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_session_artifact(self) -> "CodexSessionArtifact":
        if self.event_count < 0:
            raise ValueError("event_count must be >= 0")
        if self.last_event_at < self.started_at:
            raise ValueError("last_event_at must be >= started_at")
        return self


class CodexSuitCodeToolUse(StrictModel):
    tool_name: str
    call_count: int
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_tool_use(self) -> "CodexSuitCodeToolUse":
        if self.call_count <= 0:
            raise ValueError("call_count must be > 0")
        if self.first_seen_at and self.last_seen_at and self.last_seen_at < self.first_seen_at:
            raise ValueError("last_seen_at must be >= first_seen_at")
        return self


class CodexTranscriptMetrics(StrictModel):
    event_count: int = 0
    message_event_count: int = 0
    tool_event_count: int = 0
    assistant_message_count: int = 0
    user_message_count: int = 0
    mcp_tool_call_count: int = 0
    suitcode_tool_call_count: int = 0
    approx_input_characters: int = 0
    approx_output_characters: int = 0

    @model_validator(mode="after")
    def _validate_metrics(self) -> "CodexTranscriptMetrics":
        fields = (
            self.event_count,
            self.message_event_count,
            self.tool_event_count,
            self.assistant_message_count,
            self.user_message_count,
            self.mcp_tool_call_count,
            self.suitcode_tool_call_count,
            self.approx_input_characters,
            self.approx_output_characters,
        )
        if any(value < 0 for value in fields):
            raise ValueError("transcript metrics must be >= 0")
        return self


class CodexSessionAnalytics(StrictModel):
    agent_kind: NativeAgentKind
    session_id: str
    artifact: CodexSessionArtifact
    repository_root: str | None = None
    used_suitcode: bool
    suitcode_tools: tuple[CodexSuitCodeToolUse, ...]
    first_suitcode_tool: str | None = None
    first_suitcode_tool_index: int | None = None
    first_high_value_suitcode_tool: str | None = None
    first_high_value_suitcode_tool_index: int | None = None
    transcript_metrics: CodexTranscriptMetrics
    transcript_capture: TranscriptCapture | None = None
    token_breakdown: TranscriptTokenBreakdown | None = None
    late_suitcode_adoption: bool = False
    late_high_value_suitcode_adoption: bool = False
    used_no_high_value_suitcode_tool: bool = False
    shell_heavy_before_suitcode: bool = False
    correlation_quality: CorrelationQuality = CorrelationQuality.NONE
    correlated_analytics_session_id: str | None = None
    correlated_event_count: int = 0
    notes: tuple[str, ...] = ()

    @field_validator("session_id", "correlated_analytics_session_id")
    @classmethod
    def _validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_session(self) -> "CodexSessionAnalytics":
        if self.correlated_event_count < 0:
            raise ValueError("correlated_event_count must be >= 0")
        if not self.used_suitcode and self.suitcode_tools:
            raise ValueError("used_suitcode=False requires an empty suitcode_tools collection")
        if self.first_suitcode_tool_index is not None and self.first_suitcode_tool_index <= 0:
            raise ValueError("first_suitcode_tool_index must be > 0 when provided")
        if self.first_suitcode_tool is None and self.first_suitcode_tool_index is not None:
            raise ValueError("first_suitcode_tool_index requires first_suitcode_tool")
        if self.first_suitcode_tool is not None and not self.used_suitcode:
            raise ValueError("first_suitcode_tool requires used_suitcode=True")
        if self.first_high_value_suitcode_tool is None and self.first_high_value_suitcode_tool_index is not None:
            raise ValueError("first_high_value_suitcode_tool_index requires first_high_value_suitcode_tool")
        if self.first_high_value_suitcode_tool_index is not None and self.first_high_value_suitcode_tool_index <= 0:
            raise ValueError("first_high_value_suitcode_tool_index must be > 0 when provided")
        if self.token_breakdown is not None and self.transcript_capture is None:
            raise ValueError("token_breakdown requires transcript_capture")
        if self.transcript_capture is not None and self.transcript_capture.session_id != self.session_id:
            raise ValueError("transcript_capture session_id must match session_id")
        if self.token_breakdown is not None and self.token_breakdown.session_id != self.session_id:
            raise ValueError("token_breakdown session_id must match session_id")
        if not self.used_suitcode and (
            self.late_suitcode_adoption
            or self.late_high_value_suitcode_adoption
            or self.used_no_high_value_suitcode_tool
            or self.shell_heavy_before_suitcode
        ):
            raise ValueError("SuitCode usage flags require used_suitcode=True")
        return self


class CodexRepositoryAnalyticsSummary(StrictModel):
    repository_root: str | None = None
    session_count: int
    sessions_using_suitcode: int
    sessions_without_suitcode: int
    sessions_without_high_value_suitcode: int = 0
    sessions_with_late_suitcode_adoption: int = 0
    sessions_with_late_high_value_adoption: int = 0
    sessions_with_shell_heavy_pre_suitcode: int = 0
    skipped_artifacts: int = 0
    tool_usage: tuple[CodexSuitCodeToolUse, ...]
    first_tool_distribution: dict[str, int] = Field(default_factory=dict)
    first_high_value_tool_distribution: dict[str, int] = Field(default_factory=dict)
    correlation_quality_mix: dict[str, int] = Field(default_factory=dict)
    transcript_metrics: CodexTranscriptMetrics
    avg_first_suitcode_tool_index: float | None = None
    avg_first_high_value_suitcode_tool_index: float | None = None
    total_tokens: int | None = None
    avg_tokens_per_session: float | None = None
    avg_tokens_before_first_suitcode_tool: float | None = None
    avg_tokens_before_first_high_value_suitcode_tool: float | None = None
    token_breakdowns_by_kind: dict[str, int] = Field(default_factory=dict)
    latest_session_id: str | None = None
    latest_session_at: datetime | None = None
    notes: tuple[str, ...] = ()

    @field_validator("latest_session_id")
    @classmethod
    def _validate_latest_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("latest_session_id must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_summary(self) -> "CodexRepositoryAnalyticsSummary":
        counts = (
            self.session_count,
            self.sessions_using_suitcode,
            self.sessions_without_suitcode,
            self.sessions_without_high_value_suitcode,
            self.sessions_with_late_suitcode_adoption,
            self.sessions_with_late_high_value_adoption,
            self.sessions_with_shell_heavy_pre_suitcode,
            self.skipped_artifacts,
        )
        if any(value < 0 for value in counts):
            raise ValueError("summary counts must be >= 0")
        if self.sessions_using_suitcode + self.sessions_without_suitcode != self.session_count:
            raise ValueError("session counts are inconsistent")
        if self.sessions_without_high_value_suitcode > self.session_count:
            raise ValueError("sessions_without_high_value_suitcode is inconsistent")
        if self.sessions_with_late_suitcode_adoption > self.session_count:
            raise ValueError("sessions_with_late_suitcode_adoption is inconsistent")
        if self.sessions_with_late_high_value_adoption > self.session_count:
            raise ValueError("sessions_with_late_high_value_adoption is inconsistent")
        if self.sessions_with_shell_heavy_pre_suitcode > self.session_count:
            raise ValueError("sessions_with_shell_heavy_pre_suitcode is inconsistent")
        if self.avg_first_suitcode_tool_index is not None and self.avg_first_suitcode_tool_index <= 0:
            raise ValueError("avg_first_suitcode_tool_index must be > 0")
        if self.avg_first_high_value_suitcode_tool_index is not None and self.avg_first_high_value_suitcode_tool_index <= 0:
            raise ValueError("avg_first_high_value_suitcode_tool_index must be > 0")
        if self.total_tokens is not None and self.total_tokens < 0:
            raise ValueError("total_tokens must be >= 0")
        if self.avg_tokens_per_session is not None and self.avg_tokens_per_session < 0:
            raise ValueError("avg_tokens_per_session must be >= 0")
        if self.avg_tokens_before_first_suitcode_tool is not None and self.avg_tokens_before_first_suitcode_tool < 0:
            raise ValueError("avg_tokens_before_first_suitcode_tool must be >= 0")
        if (
            self.avg_tokens_before_first_high_value_suitcode_tool is not None
            and self.avg_tokens_before_first_high_value_suitcode_tool < 0
        ):
            raise ValueError("avg_tokens_before_first_high_value_suitcode_tool must be >= 0")
        return self
