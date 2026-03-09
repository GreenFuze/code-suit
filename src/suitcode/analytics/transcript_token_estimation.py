from __future__ import annotations

from collections import Counter

from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.native_agent_models import CodexSessionAnalytics, NativeAgentKind
from suitcode.analytics.tokenizers import OpenAiTranscriptTokenizer, TranscriptTokenizer
from suitcode.analytics.transcript_models import (
    TokenMetricKind,
    TranscriptCapture,
    TranscriptSegmentKind,
    TranscriptTokenBreakdown,
)


class TranscriptTokenEstimator:
    def __init__(self, tokenizers: tuple[TranscriptTokenizer, ...] | None = None) -> None:
        self._tokenizers = tokenizers or (OpenAiTranscriptTokenizer(),)

    def estimate_codex_session(self, session: CodexSessionAnalytics) -> CodexSessionAnalytics:
        capture = session.transcript_capture
        if capture is None:
            raise ValueError("Codex session token estimation requires transcript_capture")
        breakdown = self.estimate_capture(
            agent_kind=session.agent_kind,
            model_provider=session.artifact.model_provider,
            capture=capture,
        )
        return session.model_copy(update={"token_breakdown": breakdown})

    def estimate_capture(
        self,
        *,
        agent_kind: NativeAgentKind,
        model_provider: str | None,
        capture: TranscriptCapture,
    ) -> TranscriptTokenBreakdown:
        tokenizer = self._select_tokenizer(agent_kind=agent_kind, model_provider=model_provider)
        counts: Counter[str] = Counter()
        running_total = 0
        first_suitcode_tool: str | None = None
        first_high_value_tool: str | None = None
        tokens_before_first_suitcode_tool: int | None = None
        tokens_before_first_high_value_tool: int | None = None

        for segment in capture.segments:
            segment_tokens = tokenizer.count_segment(segment)
            if segment.kind == TranscriptSegmentKind.USER_MESSAGE:
                counts["user_message_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.ASSISTANT_MESSAGE:
                counts["assistant_message_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.MCP_TOOL_CALL:
                counts["mcp_tool_call_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.MCP_TOOL_OUTPUT:
                counts["mcp_tool_output_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.CUSTOM_TOOL_CALL:
                counts["custom_tool_call_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT:
                counts["custom_tool_output_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.TERMINAL_OUTPUT:
                counts["terminal_output_tokens"] += segment_tokens
            elif segment.kind == TranscriptSegmentKind.REASONING_SUMMARY:
                counts["reasoning_summary_tokens"] += segment_tokens

            if segment.is_suitcode and segment.kind == TranscriptSegmentKind.MCP_TOOL_CALL:
                if first_suitcode_tool is None:
                    first_suitcode_tool = segment.canonical_tool_name
                    tokens_before_first_suitcode_tool = running_total
                if (
                    segment.canonical_tool_name in HIGH_VALUE_TOOL_SET
                    and first_high_value_tool is None
                ):
                    first_high_value_tool = segment.canonical_tool_name
                    tokens_before_first_high_value_tool = running_total
            running_total += segment_tokens

        return TranscriptTokenBreakdown(
            metric_kind=TokenMetricKind.TRANSCRIPT_ESTIMATED,
            model_family=tokenizer.model_family,
            session_id=capture.session_id,
            total_tokens=running_total,
            user_message_tokens=counts["user_message_tokens"],
            assistant_message_tokens=counts["assistant_message_tokens"],
            mcp_tool_call_tokens=counts["mcp_tool_call_tokens"],
            mcp_tool_output_tokens=counts["mcp_tool_output_tokens"],
            custom_tool_call_tokens=counts["custom_tool_call_tokens"],
            custom_tool_output_tokens=counts["custom_tool_output_tokens"],
            terminal_output_tokens=counts["terminal_output_tokens"],
            reasoning_summary_tokens=counts["reasoning_summary_tokens"],
            tokens_before_first_suitcode_tool=tokens_before_first_suitcode_tool,
            tokens_before_first_high_value_suitcode_tool=tokens_before_first_high_value_tool,
            first_suitcode_tool=first_suitcode_tool,
            first_high_value_suitcode_tool=first_high_value_tool,
        )

    def _select_tokenizer(self, *, agent_kind: NativeAgentKind, model_provider: str | None) -> TranscriptTokenizer:
        for tokenizer in self._tokenizers:
            if tokenizer.supports(agent_kind, model_provider):
                return tokenizer
        raise ValueError(
            f"no transcript tokenizer available for agent `{agent_kind.value}` and model provider `{model_provider or 'unknown'}`"
        )
