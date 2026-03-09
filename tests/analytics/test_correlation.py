from __future__ import annotations

from pathlib import Path

from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.native_agent_models import CorrelationQuality
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.codex_session_parser import CodexSessionParser


def _settings(tmp_path: Path) -> AnalyticsSettings:
    return AnalyticsSettings(
        global_root=tmp_path / "global",
        repo_subdir=".suit/analytics",
        max_file_bytes=10 * 1024,
    )


def _analytics_event(event_id: str, tool_name: str, timestamp_utc: str, session_id: str = "session:local") -> AnalyticsEvent:
    return AnalyticsEvent(
        event_id=event_id,
        session_id=session_id,
        timestamp_utc=timestamp_utc,
        tool_name=tool_name,
        workspace_id="workspace:demo",
        repository_id="repo:demo",
        repository_root="C:/repo/demo",
        arguments_redacted={},
        arguments_fingerprint_sha256=f"hash-{event_id}",
        status=AnalyticsStatus.SUCCESS,
        duration_ms=1,
        output_model_type="Result",
    )


def _codex_session(tmp_path: Path) -> tuple[Path, object]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact = tmp_path / "session.jsonl"
    artifact.write_text(
        "\n".join(
            (
                f'{{"timestamp":"2026-03-08T10:00:00.000Z","type":"session_meta","payload":{{"id":"codex-session","timestamp":"2026-03-08T10:00:00.000Z","cwd":"{repo_root.as_posix()}"}}}}',
                '{"timestamp":"2026-03-08T10:00:01.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__suitcode__open_workspace","arguments":"{}","call_id":"call-open"}}',
            )
        ),
        encoding="utf-8",
    )
    return repo_root, CodexSessionParser().parse(artifact)


def test_correlation_repo_only_when_no_tool_overlap(tmp_path: Path) -> None:
    repo_root, session = _codex_session(tmp_path)
    store = JsonlAnalyticsStore(_settings(tmp_path))
    store.append_event(_analytics_event("event:1", "describe_components", "2026-03-08T10:00:02Z"), repository_root=repo_root)

    correlated = AnalyticsCorrelationService(store).correlate_codex_session(session, repo_root)

    assert correlated.correlation_quality == CorrelationQuality.REPO_ONLY


def test_correlation_tool_overlap_when_tools_match_without_timing(tmp_path: Path) -> None:
    repo_root, session = _codex_session(tmp_path)
    store = JsonlAnalyticsStore(_settings(tmp_path))
    store.append_event(_analytics_event("event:1", "open_workspace", "2026-03-08T11:30:00Z"), repository_root=repo_root)

    correlated = AnalyticsCorrelationService(store).correlate_codex_session(session, repo_root)

    assert correlated.correlation_quality == CorrelationQuality.TOOL_OVERLAP


def test_correlation_strong_when_repo_tool_and_timing_overlap(tmp_path: Path) -> None:
    repo_root, session = _codex_session(tmp_path)
    store = JsonlAnalyticsStore(_settings(tmp_path))
    store.append_event(_analytics_event("event:1", "open_workspace", "2026-03-08T10:00:02Z"), repository_root=repo_root)

    correlated = AnalyticsCorrelationService(store).correlate_codex_session(session, repo_root)

    assert correlated.correlation_quality == CorrelationQuality.STRONG
    assert correlated.correlated_event_count == 1


def test_correlation_session_only_when_session_id_matches(tmp_path: Path) -> None:
    repo_root, session = _codex_session(tmp_path)
    store = JsonlAnalyticsStore(_settings(tmp_path))
    store.append_event(
        _analytics_event("event:1", "describe_components", "2026-03-08T10:20:00Z", session_id="codex-session"),
        repository_root=repo_root,
    )

    correlated = AnalyticsCorrelationService(store).correlate_codex_session(session, repo_root)

    assert correlated.correlation_quality == CorrelationQuality.SESSION_ONLY
