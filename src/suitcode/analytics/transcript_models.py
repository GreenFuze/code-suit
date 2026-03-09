from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel


class TranscriptSegmentKind(StrEnum):
    __test__ = False
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    MCP_TOOL_CALL = "mcp_tool_call"
    MCP_TOOL_OUTPUT = "mcp_tool_output"
    CUSTOM_TOOL_CALL = "custom_tool_call"
    CUSTOM_TOOL_OUTPUT = "custom_tool_output"
    TERMINAL_OUTPUT = "terminal_output"
    REASONING_SUMMARY = "reasoning_summary"
    SYSTEM_CONTEXT = "system_context"


class TokenMetricKind(StrEnum):
    __test__ = False
    TRANSCRIPT_ESTIMATED = "transcript_estimated"
    NATIVE_REPORTED = "native_reported"
    HEURISTIC_SAVED = "heuristic_saved"


class TranscriptSegment(StrictModel):
    segment_id: str
    session_id: str
    sequence_index: int
    timestamp_utc: str
    kind: TranscriptSegmentKind
    role: str | None = None
    tool_name: str | None = None
    content_text: str
    content_bytes: int
    metadata: dict[str, object] = Field(default_factory=dict)
    is_mcp: bool = False
    is_suitcode: bool = False
    canonical_tool_name: str | None = None

    @field_validator("segment_id", "session_id", "timestamp_utc", "content_text")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_segment(self) -> "TranscriptSegment":
        if self.sequence_index <= 0:
            raise ValueError("sequence_index must be > 0")
        if self.content_bytes < 0:
            raise ValueError("content_bytes must be >= 0")
        if self.kind in {
            TranscriptSegmentKind.MCP_TOOL_CALL,
            TranscriptSegmentKind.MCP_TOOL_OUTPUT,
            TranscriptSegmentKind.CUSTOM_TOOL_CALL,
            TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT,
            TranscriptSegmentKind.TERMINAL_OUTPUT,
        } and (self.tool_name is None or not self.tool_name.strip()):
            raise ValueError("tool_name is required for tool-related transcript segments")
        if self.canonical_tool_name is not None and not self.is_suitcode:
            raise ValueError("canonical_tool_name requires is_suitcode=True")
        if self.is_suitcode and not self.is_mcp:
            raise ValueError("is_suitcode=True requires is_mcp=True")
        return self


class TranscriptCapture(StrictModel):
    session_id: str
    repository_root: str | None = None
    artifact_path: str
    segments: tuple[TranscriptSegment, ...]

    @field_validator("session_id", "artifact_path")
    @classmethod
    def _validate_capture_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_capture(self) -> "TranscriptCapture":
        seen_ids: set[str] = set()
        expected_index = 1
        for segment in self.segments:
            if segment.session_id != self.session_id:
                raise ValueError("all transcript segments must share the same session_id")
            if segment.sequence_index != expected_index:
                raise ValueError("transcript segments must have contiguous sequence_index values")
            if segment.segment_id in seen_ids:
                raise ValueError("transcript segment IDs must be unique")
            seen_ids.add(segment.segment_id)
            expected_index += 1
        return self


class TranscriptTokenBreakdown(StrictModel):
    metric_kind: TokenMetricKind
    model_family: str
    session_id: str
    total_tokens: int
    user_message_tokens: int = 0
    assistant_message_tokens: int = 0
    mcp_tool_call_tokens: int = 0
    mcp_tool_output_tokens: int = 0
    custom_tool_call_tokens: int = 0
    custom_tool_output_tokens: int = 0
    terminal_output_tokens: int = 0
    reasoning_summary_tokens: int = 0
    tokens_before_first_suitcode_tool: int | None = None
    tokens_before_first_high_value_suitcode_tool: int | None = None
    first_suitcode_tool: str | None = None
    first_high_value_suitcode_tool: str | None = None

    @field_validator("model_family", "session_id")
    @classmethod
    def _validate_token_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_breakdown(self) -> "TranscriptTokenBreakdown":
        category_counts = (
            self.user_message_tokens,
            self.assistant_message_tokens,
            self.mcp_tool_call_tokens,
            self.mcp_tool_output_tokens,
            self.custom_tool_call_tokens,
            self.custom_tool_output_tokens,
            self.terminal_output_tokens,
            self.reasoning_summary_tokens,
        )
        counts = (self.total_tokens, *category_counts)
        if any(value < 0 for value in counts):
            raise ValueError("token counts must be >= 0")
        if sum(category_counts) != self.total_tokens:
            raise ValueError("token category counts must sum to total_tokens")
        if self.first_suitcode_tool is None and self.tokens_before_first_suitcode_tool is not None:
            raise ValueError("tokens_before_first_suitcode_tool requires first_suitcode_tool")
        if self.first_high_value_suitcode_tool is None and self.tokens_before_first_high_value_suitcode_tool is not None:
            raise ValueError("tokens_before_first_high_value_suitcode_tool requires first_high_value_suitcode_tool")
        return self
