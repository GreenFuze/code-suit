from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.transcript_models import TranscriptSegmentKind


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex_sessions"


def _materialize_fixture(tmp_path: Path, fixture_name: str, repository_root: Path) -> Path:
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    artifact = tmp_path / fixture_name
    artifact.write_text(template.replace("__REPO_ROOT__", repository_root.as_posix()), encoding="utf-8")
    return artifact


def test_capture_builder_normalizes_visible_segments(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    artifact = _materialize_fixture(tmp_path, "session_with_transcript_details.jsonl", repo_root)

    capture = CodexTranscriptCaptureBuilder().build(artifact)

    assert capture.session_id == "codex-session-3"
    assert capture.repository_root == str(repo_root)
    assert [segment.kind for segment in capture.segments] == [
        TranscriptSegmentKind.USER_MESSAGE,
        TranscriptSegmentKind.CUSTOM_TOOL_CALL,
        TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT,
        TranscriptSegmentKind.REASONING_SUMMARY,
        TranscriptSegmentKind.MCP_TOOL_CALL,
        TranscriptSegmentKind.MCP_TOOL_OUTPUT,
        TranscriptSegmentKind.ASSISTANT_MESSAGE,
    ]
    assert capture.segments[0].content_text == "check this repo\nfind the right MCP tool"
    assert capture.segments[4].is_suitcode is True
    assert capture.segments[4].canonical_tool_name == "repository_summary"
    assert capture.segments[5].tool_name == "mcp__suitcode__repository_summary"
    assert capture.segments[5].content_text.startswith("tool:mcp__suitcode__repository_summary\noutput:")


def test_capture_builder_fails_fast_on_unknown_call_output(tmp_path: Path) -> None:
    artifact = tmp_path / "invalid.jsonl"
    artifact.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-03-08T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-session","timestamp":"2026-03-08T10:00:00.000Z","cwd":"C:/repo"}}',
                '{"timestamp":"2026-03-08T10:00:01.000Z","type":"response_item","payload":{"type":"function_call_output","call_id":"missing","output":"{}"}}',
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown tool output call_id"):
        CodexTranscriptCaptureBuilder().build(artifact)
