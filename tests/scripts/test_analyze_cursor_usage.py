from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import pytest

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

from scripts import analyze_cursor_usage


class _FakeService:
    def repository_summary(self, repository_root):
        return NativeRepositoryAnalyticsSummary(
            repository_root=(str(repository_root) if repository_root is not None else None),
            session_count=1,
            sessions_using_suitcode=1,
            sessions_without_suitcode=0,
            tool_usage=(NativeSuitCodeToolUse(tool_name="open_workspace", call_count=1),),
            correlation_quality_mix={"repo_only": 1},
            transcript_metrics=NativeTranscriptMetrics(event_count=3, mcp_tool_call_count=0, suitcode_tool_call_count=0),
            total_tokens=24,
        )

    def session_analytics(self, repository_root=None, session_id=None):
        sid = session_id or "cursor-session-1"
        repo_root = str(repository_root) if repository_root is not None else None
        return (
            NativeSessionAnalytics(
                agent_kind=NativeAgentKind.CURSOR,
                session_id=sid,
                artifact=NativeSessionArtifact(
                    session_id=sid,
                    artifact_path="C:/tmp/cursor.jsonl",
                    repository_root=repo_root,
                    started_at=datetime(2026, 3, 21, 10, 0, tzinfo=UTC),
                    last_event_at=datetime(2026, 3, 21, 10, 1, tzinfo=UTC),
                    cwd=repo_root,
                    event_count=3,
                ),
                repository_root=repo_root,
                used_suitcode=True,
                suitcode_tools=(NativeSuitCodeToolUse(tool_name="open_workspace", call_count=1),),
                transcript_metrics=NativeTranscriptMetrics(event_count=3),
                transcript_capture=TranscriptCapture(
                    session_id=sid,
                    repository_root=repo_root,
                    artifact_path="C:/tmp/cursor.jsonl",
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
                    total_tokens=24,
                    user_message_tokens=24,
                ),
                correlation_quality=CorrelationQuality.REPO_ONLY,
            ),
        )

    def latest_repository_session(self, repository_root):
        return self.session_analytics(repository_root=repository_root)[0]


def test_script_outputs_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_cursor_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(sys, "argv", ["analyze_cursor_usage", "--repository-root", str(tmp_path), "--json", "--include-tokens"])

    analyze_cursor_usage.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["sessions_using_suitcode"] == 1
    assert payload["sessions"][0]["agent_kind"] == "cursor"
    assert "token_breakdown" in payload["sessions"][0]
    assert "transcript_capture" not in payload["sessions"][0]


def test_script_outputs_text(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_cursor_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_cursor_usage", "--repository-root", str(tmp_path), "--latest", "--include-correlation", "--include-tokens"],
    )

    analyze_cursor_usage.main()
    output = capsys.readouterr().out

    assert "Cursor SuitCode Usage" in output
    assert "Sessions using SuitCode: 1" in output
    assert "Transcript tokens: total=24" in output
    assert "correlation=repo_only" in output


def test_limit_must_be_positive(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(analyze_cursor_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(sys, "argv", ["analyze_cursor_usage", "--repository-root", str(tmp_path), "--limit", "0"])

    with pytest.raises(ValueError, match="--limit must be > 0"):
        analyze_cursor_usage.main()
