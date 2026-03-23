from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from suitcode.analytics.native_agent_models import (
    CorrelationQuality,
    NativeAgentKind,
    NativeRepositoryAnalyticsSummary,
    NativeSessionAnalytics,
    NativeSessionArtifact,
    NativeSuitCodeToolUse,
    NativeTranscriptMetrics,
)
from suitcode.analytics.transcript_models import (
    TokenMetricKind,
    TranscriptCapture,
    TranscriptSegment,
    TranscriptSegmentKind,
    TranscriptTokenBreakdown,
)

from scripts import analyze_claude_usage


class _FakeService:
    def repository_summary(self, repository_root):
        return NativeRepositoryAnalyticsSummary(
            repository_root=(str(repository_root) if repository_root is not None else None),
            session_count=1,
            sessions_using_suitcode=1,
            sessions_without_suitcode=0,
            tool_usage=(
                NativeSuitCodeToolUse(
                    tool_name="open_workspace",
                    call_count=1,
                    first_seen_at=datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
                    last_seen_at=datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
                ),
            ),
            first_tool_distribution={"open_workspace": 1},
            correlation_quality_mix={"strong": 1},
            transcript_metrics=NativeTranscriptMetrics(
                event_count=4,
                tool_event_count=1,
                mcp_tool_call_count=1,
                suitcode_tool_call_count=1,
                native_reported_input_tokens=100,
                native_reported_output_tokens=25,
                native_reported_cache_creation_tokens=5,
                native_reported_cache_read_tokens=3,
            ),
            total_tokens=42,
            native_reported_input_tokens=100,
            native_reported_output_tokens=25,
            native_reported_cache_creation_tokens=5,
            native_reported_cache_read_tokens=3,
        )

    def session_analytics(self, repository_root=None, session_id=None):
        sid = session_id or "claude-session-1"
        repo_root = str(repository_root) if repository_root is not None else None
        return (
            NativeSessionAnalytics(
                agent_kind=NativeAgentKind.CLAUDE,
                session_id=sid,
                artifact=NativeSessionArtifact(
                    session_id=sid,
                    artifact_path="C:/tmp/claude.jsonl",
                    repository_root=repo_root,
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
                    last_event_at=datetime(2026, 3, 21, 10, 1, tzinfo=UTC),
                    cwd=repo_root,
                    cli_version="1.0.0",
                    model_provider="anthropic",
                    event_count=4,
                ),
                repository_root=repo_root,
                used_suitcode=True,
                suitcode_tools=(NativeSuitCodeToolUse(tool_name="open_workspace", call_count=1),),
                first_suitcode_tool="open_workspace",
                first_suitcode_tool_index=2,
                transcript_metrics=NativeTranscriptMetrics(
                    event_count=4,
                    tool_event_count=1,
                    mcp_tool_call_count=1,
                    suitcode_tool_call_count=1,
                    native_reported_input_tokens=100,
                    native_reported_output_tokens=25,
                ),
                transcript_capture=TranscriptCapture(
                    session_id=sid,
                    repository_root=repo_root,
                    artifact_path="C:/tmp/claude.jsonl",
                    segments=(
                        TranscriptSegment(
                            segment_id="segment:1",
                            session_id=sid,
                            sequence_index=1,
                            timestamp_utc="2026-03-21T10:00:00Z",
                            kind=TranscriptSegmentKind.USER_MESSAGE,
                            content_text="inspect repo",
                            content_bytes=12,
                        ),
                    ),
                ),
                token_breakdown=TranscriptTokenBreakdown(
                    metric_kind=TokenMetricKind.TRANSCRIPT_ESTIMATED,
                    model_family="openai/cl100k_base",
                    session_id=sid,
                    total_tokens=42,
                    user_message_tokens=42,
                    first_suitcode_tool="open_workspace",
                    tokens_before_first_suitcode_tool=10,
                ),
                correlation_quality=CorrelationQuality.STRONG,
            ),
        )

    def latest_repository_session(self, repository_root):
        return self.session_analytics(repository_root=repository_root)[0]


def test_script_outputs_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_claude_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(sys, "argv", ["analyze_claude_usage", "--repository-root", str(tmp_path), "--json"])

    analyze_claude_usage.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["sessions_using_suitcode"] == 1
    assert payload["sessions"][0]["agent_kind"] == "claude"


def test_script_outputs_text_with_tokens(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_claude_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_claude_usage", "--repository-root", str(tmp_path), "--latest", "--include-correlation", "--include-tokens"],
    )

    analyze_claude_usage.main()
    output = capsys.readouterr().out

    assert "Claude SuitCode Usage" in output
    assert "Sessions using SuitCode: 1" in output
    assert "Transcript tokens: total=42" in output
    assert "Native-reported tokens: input=100, output=25, cache_creation=5, cache_read=3" in output
