from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from suitcode.analytics.native_agent_models import (
    CorrelationQuality,
    NativeAgentKind,
    NativeSessionAnalytics,
    NativeSessionArtifact,
    NativeSuitCodeToolUse,
    NativeTranscriptMetrics,
)
from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_models import TokenMetricKind, TranscriptCapture, TranscriptSegment, TranscriptSegmentKind, TranscriptTokenBreakdown
from suitcode.providers.provider_metadata import DetectedProviderSupport, ProviderDescriptor, RepositorySupportResult
from suitcode.providers.provider_roles import ProviderRole

from scripts import analyze_dogfooding


class _FakeNativeService:
    def __init__(self, agent_kind: NativeAgentKind, session: NativeSessionAnalytics) -> None:
        self._agent_kind = agent_kind
        self._session = session

    def session_analytics(self, repository_root=None):
        return (self._session,)


def _session(agent_kind: NativeAgentKind, repo_root: Path, *, with_tool_indices: bool) -> NativeSessionAnalytics:
    session_id = f"{agent_kind.value}-session-1"
    return NativeSessionAnalytics(
        agent_kind=agent_kind,
        session_id=session_id,
        artifact=NativeSessionArtifact(
            session_id=session_id,
            artifact_path=f"C:/tmp/{session_id}.jsonl",
            repository_root=str(repo_root),
            started_at=datetime.now(UTC) - timedelta(hours=1),
            last_event_at=datetime.now(UTC),
            cwd=str(repo_root),
            event_count=4,
        ),
        repository_root=str(repo_root),
        used_suitcode=True,
        suitcode_tools=(NativeSuitCodeToolUse(tool_name="open_workspace", call_count=1),),
        first_suitcode_tool=("open_workspace" if with_tool_indices else None),
        first_suitcode_tool_index=(2 if with_tool_indices else None),
        first_high_value_suitcode_tool=("open_workspace" if with_tool_indices else None),
        first_high_value_suitcode_tool_index=(2 if with_tool_indices else None),
        transcript_metrics=NativeTranscriptMetrics(event_count=4, mcp_tool_call_count=1, suitcode_tool_call_count=1),
        transcript_capture=TranscriptCapture(
            session_id=session_id,
            repository_root=str(repo_root),
            artifact_path=f"C:/tmp/{session_id}.jsonl",
            segments=(
                TranscriptSegment(
                    segment_id="segment:1",
                    session_id=session_id,
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
            session_id=session_id,
            total_tokens=24,
            user_message_tokens=24,
            first_suitcode_tool=("open_workspace" if with_tool_indices else None),
            first_high_value_suitcode_tool=("open_workspace" if with_tool_indices else None),
            tokens_before_first_suitcode_tool=(6 if with_tool_indices else None),
            tokens_before_first_high_value_suitcode_tool=(6 if with_tool_indices else None),
        ),
        correlation_quality=CorrelationQuality.STRONG,
    )


def test_build_dogfooding_summary_aggregates_agents(monkeypatch, tmp_path: Path) -> None:
    tracked = analyze_dogfooding.TrackedRepository(
        label="repo",
        repository_root=tmp_path,
        ecosystems=("go",),
        notes=("note",),
        is_primary=False,
    )
    support = RepositorySupportResult(
        repository_root=tmp_path,
        detected_providers=(
            DetectedProviderSupport(
                descriptor=ProviderDescriptor(
                    provider_id="go",
                    display_name="go",
                    build_systems=("go",),
                    programming_languages=("go",),
                    supported_roles=frozenset({ProviderRole.ARCHITECTURE, ProviderRole.TEST}),
                ),
                detected_roles=frozenset({ProviderRole.ARCHITECTURE, ProviderRole.TEST}),
                attachments=(),
            ),
        ),
    )
    monkeypatch.setattr(analyze_dogfooding.Repository, "support_for_path", lambda path: support)
    monkeypatch.setattr(
        analyze_dogfooding,
        "build_native_services",
        lambda include_tokens=True: {
            "codex": _FakeNativeService(NativeAgentKind.CODEX, _session(NativeAgentKind.CODEX, tmp_path, with_tool_indices=True)),
            "claude": _FakeNativeService(NativeAgentKind.CLAUDE, _session(NativeAgentKind.CLAUDE, tmp_path, with_tool_indices=True)),
            "cursor": _FakeNativeService(NativeAgentKind.CURSOR, _session(NativeAgentKind.CURSOR, tmp_path, with_tool_indices=False)),
        },
    )
    monkeypatch.setattr(
        analyze_dogfooding,
        "summarize_mcp_events",
        lambda repository_root, since, include_global: {
            "total_calls": 3,
            "estimated_tokens": 10,
            "estimated_tokens_saved": 5,
            "top_tools": ("open_workspace",),
            "inefficiency_mix": {"unused_tool": 1},
            "inefficiency_count": 1,
        },
    )

    summary = analyze_dogfooding.build_dogfooding_summary(
        tracked=tracked,
        days=14,
        include_global_mcp=False,
        session_limit=100,
    )

    assert summary["support"]["provider_ids"] == ("go",)
    assert summary["mcp_analytics"]["total_calls"] == 3
    assert len(summary["agents"]) == 3
    cursor = next(item for item in summary["agents"] if item["agent_kind"] == "cursor")
    assert any("partial" in note.lower() for note in cursor["notes"])


def test_main_writes_bundle(monkeypatch, capsys, tmp_path: Path) -> None:
    tracked = analyze_dogfooding.TrackedRepository(
        label="repo",
        repository_root=tmp_path,
        ecosystems=("go",),
        notes=tuple(),
        is_primary=False,
    )
    monkeypatch.setattr(analyze_dogfooding, "resolve_tracked_repository", lambda repository_root, tracked_label: tracked)
    monkeypatch.setattr(
        analyze_dogfooding,
        "build_dogfooding_summary",
        lambda tracked, days, include_global_mcp, session_limit: {
            "generated_at_utc": "2026-03-21T10:00:00Z",
            "window_start_utc": "2026-03-07T10:00:00Z",
            "window_end_utc": "2026-03-21T10:00:00Z",
            "tracked_repository": {
                "label": tracked.label,
                "repository_root": str(tracked.repository_root),
                "ecosystems": tracked.ecosystems,
                "notes": tracked.notes,
                "is_primary": tracked.is_primary,
            },
            "support": {"is_supported": True, "provider_ids": ("go",), "repository_root": str(tracked.repository_root)},
            "mcp_analytics": {
                "total_calls": 1,
                "estimated_tokens": 2,
                "estimated_tokens_saved": 1,
                "top_tools": ("open_workspace",),
                "inefficiency_mix": {},
                "inefficiency_count": 0,
            },
            "agents": (
                {
                    "agent_kind": "codex",
                    "session_count": 1,
                    "sessions_using_suitcode": 1,
                    "avg_first_suitcode_tool_index": 2.0,
                    "avg_first_high_value_suitcode_tool_index": 2.0,
                    "total_tokens": 24,
                    "avg_tokens_before_first_suitcode_tool": 6.0,
                    "avg_tokens_before_first_high_value_suitcode_tool": 6.0,
                    "correlation_quality_mix": {"strong": 1},
                    "top_tools": ({"tool_name": "open_workspace"},),
                    "notes": (),
                },
            ),
        },
    )
    output_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["analyze_dogfooding", "--tracked-label", "repo", "--output-dir", str(output_dir)],
    )

    analyze_dogfooding.main()
    output = capsys.readouterr().out

    assert "Dogfooding summary written:" in output
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "summary.md").exists()
    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert payload["support"]["provider_ids"] == ["go"]


def test_summarize_mcp_events_matches_nested_repository_scope(monkeypatch, tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    nested_root = repo_root / "server"
    nested_root.mkdir(parents=True)
    settings = AnalyticsSettings(
        global_root=(tmp_path / "global").resolve(),
        repo_subdir=".suit/analytics",
        max_file_bytes=1024 * 1024,
    )
    store = JsonlAnalyticsStore(settings)
    store.append_event(
        AnalyticsEvent(
            event_id="event-1",
            session_id="session-1",
            timestamp_utc="2026-03-21T10:00:00Z",
            tool_name="understand_repository",
            repository_root=str(repo_root),
            arguments_fingerprint_sha256="hash-1",
            status=AnalyticsStatus.SUCCESS,
            duration_ms=5,
        ),
        repository_root=repo_root,
    )
    monkeypatch.setattr(analyze_dogfooding.AnalyticsSettings, "from_env", classmethod(lambda cls: settings))

    summary = analyze_dogfooding.summarize_mcp_events(
        repository_root=nested_root,
        since=datetime(2026, 3, 20, tzinfo=UTC),
        include_global=False,
    )

    assert summary["total_calls"] == 1
    assert summary["top_tools"] == ("understand_repository",)
