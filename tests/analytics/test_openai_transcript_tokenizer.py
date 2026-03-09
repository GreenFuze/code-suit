from __future__ import annotations

from suitcode.analytics.native_agent_models import NativeAgentKind
from suitcode.analytics.tokenizers.openai_transcript_tokenizer import OpenAiTranscriptTokenizer
from suitcode.analytics.transcript_models import TranscriptSegment, TranscriptSegmentKind


def test_openai_tokenizer_counts_text_deterministically() -> None:
    tokenizer = OpenAiTranscriptTokenizer()

    assert tokenizer.supports(NativeAgentKind.CODEX, "openai") is True
    assert tokenizer.supports(NativeAgentKind.CODEX, None) is True
    assert tokenizer.count_text("repository summary") > 0


def test_openai_tokenizer_counts_transcript_segments() -> None:
    tokenizer = OpenAiTranscriptTokenizer()
    segment = TranscriptSegment(
        segment_id="segment:1",
        session_id="codex-session",
        sequence_index=1,
        timestamp_utc="2026-03-08T10:00:00Z",
        kind=TranscriptSegmentKind.MCP_TOOL_CALL,
        tool_name="mcp__suitcode__repository_summary",
        content_text='tool:mcp__suitcode__repository_summary\narguments:{"workspace_id":"w"}',
        content_bytes=64,
        is_mcp=True,
        is_suitcode=True,
        canonical_tool_name="repository_summary",
    )

    assert tokenizer.count_segment(segment) > 0
