from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import pytest

from suitcode.analytics.native_agent_models import (
    CodexRepositoryAnalyticsSummary,
    CodexSessionAnalytics,
    CodexSessionArtifact,
    CodexSuitCodeToolUse,
    CodexTranscriptMetrics,
    CorrelationQuality,
    NativeAgentKind,
)
from suitcode.analytics.transcript_models import (
    TokenMetricKind,
    TranscriptCapture,
    TranscriptSegment,
    TranscriptSegmentKind,
    TranscriptTokenBreakdown,
)

from scripts import analyze_codex_usage


class _FakeService:
    def repository_summary(self, repository_root):
        return CodexRepositoryAnalyticsSummary(
            repository_root=(str(repository_root) if repository_root is not None else None),
            session_count=1,
            sessions_using_suitcode=1,
            sessions_without_suitcode=0,
            sessions_without_high_value_suitcode=0,
            sessions_with_late_suitcode_adoption=1,
            sessions_with_late_high_value_adoption=1,
            sessions_with_shell_heavy_pre_suitcode=1,
            tool_usage=(
                CodexSuitCodeToolUse(
                    tool_name="open_workspace",
                    call_count=1,
                    first_seen_at=datetime(2026, 3, 8, 10, 0, tzinfo=UTC),
                    last_seen_at=datetime(2026, 3, 8, 10, 0, tzinfo=UTC),
                ),
            ),
            first_tool_distribution={"open_workspace": 1},
            first_high_value_tool_distribution={"open_workspace": 1},
            correlation_quality_mix={"strong": 1},
            transcript_metrics=CodexTranscriptMetrics(event_count=4, tool_event_count=2, mcp_tool_call_count=1, suitcode_tool_call_count=1),
            avg_first_suitcode_tool_index=7.0,
            avg_first_high_value_suitcode_tool_index=7.0,
            total_tokens=42,
            avg_tokens_per_session=42.0,
            avg_tokens_before_first_suitcode_tool=10.0,
            avg_tokens_before_first_high_value_suitcode_tool=10.0,
            token_breakdowns_by_kind={"mcp_tool_call_tokens": 12},
            latest_session_id="codex-session-1",
            latest_session_at=datetime(2026, 3, 8, 10, 0, tzinfo=UTC),
        )

    def session_analytics(self, repository_root=None, session_id=None):
        return (
            CodexSessionAnalytics(
                agent_kind=NativeAgentKind.CODEX,
                session_id=session_id or "codex-session-1",
                artifact=CodexSessionArtifact(
                    session_id=session_id or "codex-session-1",
                    artifact_path="C:/tmp/session.jsonl",
                    repository_root=(str(repository_root) if repository_root is not None else None),
                    started_at=datetime(2026, 3, 8, 10, 0, tzinfo=UTC),
                    last_event_at=datetime(2026, 3, 8, 10, 1, tzinfo=UTC),
                    cwd=(str(repository_root) if repository_root is not None else None),
                    cli_version="0.105.0",
                    model_provider="openai",
                    event_count=4,
                ),
                repository_root=(str(repository_root) if repository_root is not None else None),
                used_suitcode=True,
                suitcode_tools=(CodexSuitCodeToolUse(tool_name="open_workspace", call_count=1),),
                first_suitcode_tool="open_workspace",
                first_suitcode_tool_index=7,
                first_high_value_suitcode_tool="open_workspace",
                first_high_value_suitcode_tool_index=7,
                late_suitcode_adoption=True,
                late_high_value_suitcode_adoption=True,
                used_no_high_value_suitcode_tool=False,
                shell_heavy_before_suitcode=True,
                transcript_metrics=CodexTranscriptMetrics(event_count=4, tool_event_count=2, mcp_tool_call_count=1, suitcode_tool_call_count=1),
                transcript_capture=TranscriptCapture(
                    session_id=session_id or "codex-session-1",
                    repository_root=(str(repository_root) if repository_root is not None else None),
                    artifact_path="C:/tmp/session.jsonl",
                    segments=(
                        TranscriptSegment(
                            segment_id="segment:1",
                            session_id=session_id or "codex-session-1",
                            sequence_index=1,
                            timestamp_utc="2026-03-08T10:00:00Z",
                            kind=TranscriptSegmentKind.USER_MESSAGE,
                            content_text="inspect repo",
                            content_bytes=12,
                        ),
                    ),
                ),
                token_breakdown=TranscriptTokenBreakdown(
                    metric_kind=TokenMetricKind.TRANSCRIPT_ESTIMATED,
                    model_family="openai/codex",
                    session_id=session_id or "codex-session-1",
                    total_tokens=42,
                    user_message_tokens=42,
                    first_suitcode_tool="open_workspace",
                    first_high_value_suitcode_tool="open_workspace",
                    tokens_before_first_suitcode_tool=10,
                    tokens_before_first_high_value_suitcode_tool=10,
                ),
                correlation_quality=CorrelationQuality.STRONG,
                correlated_event_count=1,
            ),
        )

    def latest_repository_session(self, repository_root):
        return self.session_analytics(repository_root=repository_root)[0]


def test_script_outputs_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_codex_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_codex_usage", "--repository-root", str(tmp_path), "--json"],
    )

    analyze_codex_usage.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["sessions_using_suitcode"] == 1
    assert payload["summary"]["sessions_with_late_suitcode_adoption"] == 1
    assert payload["sessions"][0]["first_suitcode_tool"] == "open_workspace"


def test_script_outputs_text(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_codex_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_codex_usage", "--repository-root", str(tmp_path), "--latest", "--include-correlation"],
    )

    analyze_codex_usage.main()
    output = capsys.readouterr().out

    assert "Codex SuitCode Usage" in output
    assert "Sessions using SuitCode: 1" in output
    assert "Late SuitCode adoption sessions: 1" in output
    assert "open_workspace" in output


def test_script_outputs_token_details(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_codex_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_codex_usage", "--repository-root", str(tmp_path), "--latest", "--include-tokens", "--show-segments"],
    )

    analyze_codex_usage.main()
    output = capsys.readouterr().out

    assert "Token estimation enabled: True" in output
    assert "Transcript tokens: total=42" in output
    assert "shell_heavy=True" in output
    assert "[1] user_message" in output


def test_show_segments_requires_include_tokens(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(analyze_codex_usage, "build_service", lambda include_correlation, include_tokens: _FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_codex_usage", "--repository-root", str(tmp_path), "--show-segments"],
    )

    with pytest.raises(ValueError, match="--show-segments requires --include-tokens"):
        analyze_codex_usage.main()
