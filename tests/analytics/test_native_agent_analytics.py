from __future__ import annotations

import shutil
from pathlib import Path

from suitcode.analytics.claude_analytics_service import ClaudeAnalyticsService
from suitcode.analytics.claude_session_store import ClaudeSessionStore
from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.cursor_analytics_service import CursorAnalyticsService
from suitcode.analytics.cursor_session_store import CursorSessionStore
from suitcode.analytics.cursor_transcript_capture import CursorTranscriptCaptureBuilder
from suitcode.analytics.native_agent_models import CorrelationQuality, NativeAgentKind
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / 'fixtures'


def _write_fixture(target: Path, fixture_name: str, repository_root: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding='utf-8')
    target.write_text(template.replace('__REPO_ROOT__', repository_root.as_posix()), encoding='utf-8')


def test_claude_repository_summary_and_tokens(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    repo_root.mkdir()
    projects_root = tmp_path / 'claude-projects'
    session_path = projects_root / 'repo' / 'claude-session-1.jsonl'
    _write_fixture(session_path, 'claude_sessions/session_with_suitcode.jsonl', repo_root)

    service = ClaudeAnalyticsService(
        ClaudeSessionStore(projects_root),
        capture_builder=ClaudeTranscriptCaptureBuilder(),
        token_estimator=TranscriptTokenEstimator(),
    )

    summary = service.repository_summary(repo_root)
    session = service.latest_repository_session(repo_root)

    assert summary.session_count == 1
    assert summary.sessions_using_suitcode == 1
    assert summary.first_tool_distribution == {'open_workspace': 1}
    assert summary.first_high_value_tool_distribution == {'analyze_change': 1}
    assert summary.total_tokens is not None and summary.total_tokens > 0
    assert summary.native_reported_input_tokens == 140
    assert summary.native_reported_output_tokens == 30
    assert session is not None
    assert session.agent_kind == NativeAgentKind.CLAUDE
    assert session.used_suitcode is True
    assert session.first_suitcode_tool == 'open_workspace'
    assert session.first_high_value_suitcode_tool == 'analyze_change'
    assert session.transcript_capture is not None
    assert session.token_breakdown is not None


def test_claude_store_matches_nested_repository_scope(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    nested_root = repo_root / 'server'
    nested_root.mkdir(parents=True)
    projects_root = tmp_path / 'claude-projects'
    session_path = projects_root / 'repo' / 'claude-session-1.jsonl'
    _write_fixture(session_path, 'claude_sessions/session_with_suitcode.jsonl', repo_root)

    sessions = ClaudeSessionStore(projects_root).list_sessions(repository_root=nested_root)

    assert len(sessions) == 1
    assert sessions[0].name == 'claude-session-1.jsonl'


def test_cursor_summary_can_correlate_without_native_tool_visibility(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    repo_root.mkdir()
    projects_root = tmp_path / 'cursor-projects'
    project_root = projects_root / 'repo-project'
    transcript_path = project_root / 'agent-transcripts' / 'cursor-session-1.jsonl'
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    _write_fixture(transcript_path, 'cursor_sessions/session_without_tools.jsonl', repo_root)
    (project_root / 'worker.log').write_text(f'[info] workspacePath={repo_root.as_posix()}\n', encoding='utf-8')

    analytics_store = JsonlAnalyticsStore(
        AnalyticsSettings(
            global_root=(tmp_path / 'analytics').resolve(),
            repo_subdir='.suit/analytics',
            max_file_bytes=1024 * 1024,
        )
    )
    analytics_store.append_event(
        AnalyticsEvent(
            event_id='event-1',
            session_id='other-session',
            timestamp_utc='2026-03-20T11:00:00Z',
            tool_name='open_workspace',
            repository_root=str(repo_root),
            arguments_fingerprint_sha256='abc',
            status=AnalyticsStatus.SUCCESS,
            duration_ms=10,
        ),
        repository_root=repo_root,
    )

    service = CursorAnalyticsService(
        CursorSessionStore(projects_root),
        correlation_service=AnalyticsCorrelationService(analytics_store),
        capture_builder=CursorTranscriptCaptureBuilder(CursorSessionStore(projects_root)),
        token_estimator=TranscriptTokenEstimator(),
    )

    summary = service.repository_summary(repo_root)
    session = service.latest_repository_session(repo_root)

    assert summary.session_count == 1
    assert summary.sessions_using_suitcode == 1
    assert summary.first_tool_distribution == {'open_workspace': 1}
    assert summary.total_tokens is not None and summary.total_tokens > 0
    assert session is not None
    assert session.used_suitcode is True
    assert len(session.suitcode_tools) == 1
    assert session.suitcode_tools[0].tool_name == 'open_workspace'
    assert session.suitcode_tools[0].call_count == 1
    assert session.first_suitcode_tool == 'open_workspace'
    assert session.correlation_quality == CorrelationQuality.STRONG
    assert session.correlated_event_count == 1
    assert any('synthesized' in note.lower() for note in session.notes)


def test_cursor_store_matches_nested_repository_scope(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    nested_root = repo_root / 'server'
    nested_root.mkdir(parents=True)
    projects_root = tmp_path / 'cursor-projects'
    project_root = projects_root / 'repo-project'
    transcript_path = project_root / 'agent-transcripts' / 'cursor-session-1.jsonl'
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    _write_fixture(transcript_path, 'cursor_sessions/session_without_tools.jsonl', repo_root)
    (project_root / 'worker.log').write_text(f'[info] workspacePath={repo_root.as_posix()}\n', encoding='utf-8')

    sessions = CursorSessionStore(projects_root).list_sessions(repository_root=nested_root)

    assert len(sessions) == 1
    assert sessions[0].name == 'cursor-session-1.jsonl'


def test_cursor_parser_extracts_best_effort_tool_use_when_present(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    repo_root.mkdir()
    projects_root = tmp_path / 'cursor-projects'
    project_root = projects_root / 'repo-project'
    transcript_path = project_root / 'agent-transcripts' / 'cursor-session-2.jsonl'
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    _write_fixture(transcript_path, 'cursor_sessions/session_with_tool.jsonl', repo_root)
    (project_root / 'worker.log').write_text(f'[info] workspacePath={repo_root.as_posix()}\n', encoding='utf-8')

    service = CursorAnalyticsService(
        CursorSessionStore(projects_root),
        capture_builder=CursorTranscriptCaptureBuilder(CursorSessionStore(projects_root)),
        token_estimator=TranscriptTokenEstimator(),
    )
    session = service.latest_repository_session(repo_root)

    assert session is not None
    assert session.agent_kind == NativeAgentKind.CURSOR
    assert session.used_suitcode is True
    assert session.first_suitcode_tool == 'open_workspace'
    assert session.token_breakdown is not None


def test_cursor_directory_session_layout_is_discovered_and_correlated(tmp_path: Path) -> None:
    repo_root = (tmp_path / 'repo').resolve()
    repo_root.mkdir()
    projects_root = tmp_path / 'cursor-projects'
    project_root = projects_root / 'repo-project'
    session_dir = project_root / 'agent-transcripts' / 'cursor-session-3'
    transcript_path = session_dir / 'cursor-session-3.jsonl'
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    _write_fixture(transcript_path, 'cursor_sessions/session_with_tool.jsonl', repo_root)
    (project_root / 'worker.log').write_text(f'[info] workspacePath={repo_root.as_posix()}\n', encoding='utf-8')

    service = CursorAnalyticsService(
        CursorSessionStore(projects_root),
        capture_builder=CursorTranscriptCaptureBuilder(CursorSessionStore(projects_root)),
        token_estimator=TranscriptTokenEstimator(),
    )
    session = service.latest_repository_session(repo_root)

    assert session is not None
    assert session.session_id == 'cursor-session-3'
    assert session.repository_root == str(repo_root)
    assert session.used_suitcode is True
    assert session.first_suitcode_tool == 'open_workspace'
