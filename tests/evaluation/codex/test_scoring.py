from __future__ import annotations

from datetime import UTC, datetime

from suitcode.analytics.native_agent_models import (
    CodexSessionAnalytics,
    CodexSessionArtifact,
    CodexSuitCodeToolUse,
    CodexTranscriptMetrics,
    CorrelationQuality,
    NativeAgentKind,
)
from suitcode.analytics.transcript_models import TranscriptCapture, TranscriptSegment, TranscriptSegmentKind
from suitcode.analytics.transcript_models import TokenMetricKind, TranscriptTokenBreakdown
from suitcode.evaluation.codex.scoring import CodexEvaluationScorer


def _session() -> CodexSessionAnalytics:
    return CodexSessionAnalytics(
        agent_kind=NativeAgentKind.CODEX,
        session_id="codex-session",
        artifact=CodexSessionArtifact(
            session_id="codex-session",
            artifact_path="C:/tmp/session.jsonl",
            started_at=datetime(2026, 3, 8, 10, 0, tzinfo=UTC),
            last_event_at=datetime(2026, 3, 8, 10, 1, tzinfo=UTC),
            event_count=5,
            model_provider="openai",
        ),
        repository_root="C:/repo",
        used_suitcode=True,
        suitcode_tools=(
            CodexSuitCodeToolUse(tool_name="open_workspace", call_count=1),
            CodexSuitCodeToolUse(tool_name="repository_summary", call_count=1),
        ),
        first_suitcode_tool="open_workspace",
        first_suitcode_tool_index=1,
        first_high_value_suitcode_tool="repository_summary",
        first_high_value_suitcode_tool_index=2,
        transcript_metrics=CodexTranscriptMetrics(tool_event_count=2, mcp_tool_call_count=2, suitcode_tool_call_count=2),
        correlation_quality=CorrelationQuality.STRONG,
        transcript_capture=TranscriptCapture(
            session_id="codex-session",
            artifact_path="C:/tmp/session.jsonl",
            segments=(
                TranscriptSegment(
                    segment_id="s1",
                    session_id="codex-session",
                    sequence_index=1,
                    timestamp_utc="2026-03-08T10:00:00Z",
                    kind=TranscriptSegmentKind.MCP_TOOL_CALL,
                    tool_name="mcp__suitcode__open_workspace",
                    content_text='tool:mcp__suitcode__open_workspace\narguments:{"repository_path":"."}',
                    content_bytes=60,
                    metadata={"arguments_text": '{"repository_path":"."}'},
                    is_mcp=True,
                    is_suitcode=True,
                    canonical_tool_name="open_workspace",
                ),
                TranscriptSegment(
                    segment_id="s2",
                    session_id="codex-session",
                    sequence_index=2,
                    timestamp_utc="2026-03-08T10:00:01Z",
                    kind=TranscriptSegmentKind.MCP_TOOL_CALL,
                    tool_name="mcp__suitcode__repository_summary",
                    content_text='tool:mcp__suitcode__repository_summary\narguments:{"workspace_id":"workspace:demo","repository_id":"repo:demo"}',
                    content_bytes=110,
                    metadata={"arguments_text": '{"workspace_id":"workspace:demo","repository_id":"repo:demo"}'},
                    is_mcp=True,
                    is_suitcode=True,
                    canonical_tool_name="repository_summary",
                ),
            ),
        ),
        token_breakdown=TranscriptTokenBreakdown(
            metric_kind=TokenMetricKind.TRANSCRIPT_ESTIMATED,
            model_family="openai/codex",
            session_id="codex-session",
            total_tokens=10,
            mcp_tool_call_tokens=10,
            first_suitcode_tool="open_workspace",
            first_high_value_suitcode_tool="repository_summary",
            tokens_before_first_suitcode_tool=0,
            tokens_before_first_high_value_suitcode_tool=5,
        ),
    )


def test_scorer_scores_required_tools_and_arguments() -> None:
    scorer = CodexEvaluationScorer()
    session = _session()

    tool_selection = scorer.tool_selection_score(session, required_tools=("open_workspace", "repository_summary"))
    argument_scores = scorer.argument_scores(
        session,
        expected_argument_subsets=(("repository_summary", {"workspace_id": "workspace:demo", "repository_id": "repo:demo"}),),
    )

    assert tool_selection.required_tools_present is True
    assert tool_selection.first_high_value_tool == "repository_summary"
    assert argument_scores[0].matched is True


def test_answer_score_can_ignore_non_substantive_fields() -> None:
    scorer = CodexEvaluationScorer()

    score = scorer.answer_score(
        actual_answer={
            "workspace_id": "",
            "repository_id": "",
            "provider_ids": ["python"],
            "component_count": 1,
        },
        expected_answer={
            "workspace_id": "workspace:python",
            "repository_id": "repo:python",
            "provider_ids": ["python"],
            "component_count": 1,
        },
        schema_valid=True,
        ignored_fields=("workspace_id", "repository_id"),
    )

    assert score.schema_valid is True
    assert score.missing_fields == tuple()
    assert score.mismatched_fields == tuple()
    assert score.field_matches == {"provider_ids": True, "component_count": True}
