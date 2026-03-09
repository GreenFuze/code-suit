from __future__ import annotations

from pathlib import Path

from suitcode.analytics.codex_analytics_service import CodexAnalyticsService
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex_sessions"


def _write_session(target: Path, fixture_name: str, repository_root: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    target.write_text(template.replace("__REPO_ROOT__", repository_root.as_posix()), encoding="utf-8")


def test_repository_summary_aggregates_suitcode_usage(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    _write_session(sessions_root / "2026" / "03" / "08" / "a.jsonl", "session_with_suitcode.jsonl", repo_root)
    _write_session(sessions_root / "2026" / "03" / "09" / "b.jsonl", "session_without_suitcode.jsonl", repo_root)

    service = CodexAnalyticsService(CodexSessionStore(sessions_root))
    summary = service.repository_summary(repo_root)

    assert summary.session_count == 2
    assert summary.sessions_using_suitcode == 1
    assert summary.sessions_without_suitcode == 1
    assert summary.sessions_without_high_value_suitcode == 0
    assert summary.tool_usage[0].tool_name == "open_workspace"
    assert summary.first_tool_distribution == {"open_workspace": 1}


def test_repository_summary_flags_late_and_shell_heavy_usage(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    fixture = sessions_root / "2026" / "03" / "08" / "a.jsonl"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-03-08T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-late","timestamp":"2026-03-08T10:00:00.000Z","cwd":"%s","model_provider":"openai"}}' % repo_root.as_posix(),
                '{"timestamp":"2026-03-08T10:00:01.000Z","type":"response_item","payload":{"type":"function_call","name":"shell_command","arguments":"{\\"command\\":\\"rg a\\"}","call_id":"call-1"}}',
                '{"timestamp":"2026-03-08T10:00:02.000Z","type":"response_item","payload":{"type":"function_call","name":"shell_command","arguments":"{\\"command\\":\\"rg b\\"}","call_id":"call-2"}}',
                '{"timestamp":"2026-03-08T10:00:03.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__other__search","arguments":"{}","call_id":"call-3"}}',
                '{"timestamp":"2026-03-08T10:00:04.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__other__grep","arguments":"{}","call_id":"call-4"}}',
                '{"timestamp":"2026-03-08T10:00:05.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__other__more","arguments":"{}","call_id":"call-5"}}',
                '{"timestamp":"2026-03-08T10:00:06.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__other__still_more","arguments":"{}","call_id":"call-6"}}',
                '{"timestamp":"2026-03-08T10:00:07.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__suitcode__open_workspace","arguments":"{\\"repository_path\\":\\"%s\\"}","call_id":"call-7"}}' % repo_root.as_posix(),
                '{"timestamp":"2026-03-08T10:00:08.000Z","type":"response_item","payload":{"type":"function_call","name":"mcp__suitcode__analyze_change","arguments":"{\\"workspace_id\\":\\"workspace:demo\\",\\"repository_id\\":\\"repo:demo\\",\\"repository_rel_path\\":\\"src/x.py\\"}","call_id":"call-8"}}',
            )
        ),
        encoding="utf-8",
    )

    service = CodexAnalyticsService(CodexSessionStore(sessions_root), capture_builder=CodexTranscriptCaptureBuilder())
    summary = service.repository_summary(repo_root)
    session = service.latest_repository_session(repo_root)

    assert session is not None
    assert session.late_suitcode_adoption
    assert session.late_high_value_suitcode_adoption
    assert session.shell_heavy_before_suitcode
    assert summary.sessions_with_late_suitcode_adoption == 1
    assert summary.sessions_with_late_high_value_adoption == 1
    assert summary.sessions_with_shell_heavy_pre_suitcode == 1


def test_repository_summary_skips_broken_artifacts(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    _write_session(sessions_root / "2026" / "03" / "08" / "a.jsonl", "session_with_suitcode.jsonl", repo_root)
    broken = sessions_root / "2026" / "03" / "09" / "broken.jsonl"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text('{"timestamp":"2026-03-08T10:00:00.000Z","type":"response_item","payload":{"type":"message"}}\n', encoding="utf-8")

    summary = CodexAnalyticsService(CodexSessionStore(sessions_root)).repository_summary(repo_root)

    assert summary.session_count == 1
    assert summary.skipped_artifacts == 1
    assert summary.notes


def test_latest_repository_session_returns_latest_match(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    first = sessions_root / "2026" / "03" / "08" / "a.jsonl"
    second = sessions_root / "2026" / "03" / "09" / "b.jsonl"
    _write_session(first, "session_with_suitcode.jsonl", repo_root)
    _write_session(second, "session_without_suitcode.jsonl", repo_root)

    first.touch()
    second.touch()

    latest = CodexAnalyticsService(CodexSessionStore(sessions_root)).latest_repository_session(repo_root)

    assert latest is not None
    assert latest.session_id == "codex-session-2"


def test_repository_summary_includes_token_metrics_when_enabled(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    sessions_root = tmp_path / "sessions"
    _write_session(sessions_root / "2026" / "03" / "08" / "a.jsonl", "session_with_transcript_details.jsonl", repo_root)

    service = CodexAnalyticsService(
        CodexSessionStore(sessions_root),
        capture_builder=CodexTranscriptCaptureBuilder(),
        token_estimator=TranscriptTokenEstimator(),
    )
    summary = service.repository_summary(repo_root)
    latest = service.latest_repository_session(repo_root)

    assert summary.total_tokens is not None
    assert summary.total_tokens > 0
    assert summary.avg_tokens_per_session is not None
    assert summary.token_breakdowns_by_kind["mcp_tool_call_tokens"] > 0
    assert summary.avg_tokens_before_first_suitcode_tool is not None
    assert latest is not None
    assert latest.transcript_capture is not None
    assert latest.token_breakdown is not None
