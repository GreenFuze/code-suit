from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.analytics.codex_session_parser import CodexSessionParser


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex_sessions"


def _materialize_fixture(tmp_path: Path, fixture_name: str, repository_root: Path) -> Path:
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    rendered = template.replace("__REPO_ROOT__", repository_root.as_posix())
    artifact = tmp_path / fixture_name
    artifact.write_text(rendered, encoding="utf-8")
    return artifact


def test_parser_extracts_suitcode_usage_and_metrics(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact = _materialize_fixture(tmp_path, "session_with_suitcode.jsonl", repository_root)

    parsed = CodexSessionParser().parse(artifact)

    assert parsed.session_id == "codex-session-1"
    assert parsed.repository_root == str(repository_root.resolve())
    assert parsed.used_suitcode is True
    assert tuple(item.tool_name for item in parsed.suitcode_tools) == ("open_workspace", "repository_summary")
    assert parsed.first_suitcode_tool == "open_workspace"
    assert parsed.first_suitcode_tool_index == 3
    assert parsed.transcript_metrics.event_count == 7
    assert parsed.transcript_metrics.message_event_count == 2
    assert parsed.transcript_metrics.tool_event_count == 4
    assert parsed.transcript_metrics.mcp_tool_call_count == 3
    assert parsed.transcript_metrics.suitcode_tool_call_count == 2
    assert parsed.transcript_metrics.user_message_count == 1
    assert parsed.transcript_metrics.assistant_message_count == 1
    assert parsed.transcript_metrics.approx_input_characters > 0
    assert parsed.transcript_metrics.approx_output_characters > 0


def test_parser_ignores_non_suitcode_tools(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact = _materialize_fixture(tmp_path, "session_without_suitcode.jsonl", repository_root)

    parsed = CodexSessionParser().parse(artifact)

    assert parsed.used_suitcode is False
    assert parsed.suitcode_tools == ()
    assert parsed.first_suitcode_tool is None
    assert parsed.first_suitcode_tool_index is None
    assert parsed.transcript_metrics.mcp_tool_call_count == 1
    assert parsed.transcript_metrics.suitcode_tool_call_count == 0


def test_parser_fails_fast_on_invalid_tool_call_shape(tmp_path: Path) -> None:
    artifact = tmp_path / "invalid.jsonl"
    artifact.write_text(
        "\n".join(
            (
                '{"timestamp":"2026-03-08T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-session-3","timestamp":"2026-03-08T10:00:00.000Z","cwd":"C:/repo"}}',
                '{"timestamp":"2026-03-08T10:00:01.000Z","type":"response_item","payload":{"type":"function_call","call_id":"call-bad"}}',
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid tool call name"):
        CodexSessionParser().parse(artifact)
