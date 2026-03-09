from __future__ import annotations

from pathlib import Path

from suitcode.analytics.codex_session_parser import CodexSessionParser
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.analytics.transcript_models import TokenMetricKind


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "codex_sessions"


def _materialize_fixture(tmp_path: Path, fixture_name: str, repository_root: Path) -> Path:
    template = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    artifact = tmp_path / fixture_name
    artifact.write_text(template.replace("__REPO_ROOT__", repository_root.as_posix()), encoding="utf-8")
    return artifact


def test_estimator_counts_tokens_before_first_suitcode_tool(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    artifact = _materialize_fixture(tmp_path, "session_with_transcript_details.jsonl", repo_root)
    session = CodexSessionParser().parse(artifact).model_copy(
        update={"transcript_capture": CodexTranscriptCaptureBuilder().build(artifact)}
    )

    estimated = TranscriptTokenEstimator().estimate_codex_session(session)

    assert estimated.token_breakdown is not None
    assert estimated.token_breakdown.metric_kind == TokenMetricKind.TRANSCRIPT_ESTIMATED
    assert estimated.token_breakdown.total_tokens > 0
    assert estimated.token_breakdown.first_suitcode_tool == "repository_summary"
    assert estimated.token_breakdown.first_high_value_suitcode_tool == "repository_summary"
    assert estimated.token_breakdown.tokens_before_first_suitcode_tool is not None
    assert (
        estimated.token_breakdown.tokens_before_first_high_value_suitcode_tool
        == estimated.token_breakdown.tokens_before_first_suitcode_tool
    )


def test_estimator_handles_sessions_without_suitcode(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    repo_root.mkdir()
    artifact = _materialize_fixture(tmp_path, "session_without_suitcode.jsonl", repo_root)
    session = CodexSessionParser().parse(artifact).model_copy(
        update={"transcript_capture": CodexTranscriptCaptureBuilder().build(artifact)}
    )

    estimated = TranscriptTokenEstimator().estimate_codex_session(session)

    assert estimated.token_breakdown is not None
    assert estimated.token_breakdown.total_tokens > 0
    assert estimated.token_breakdown.first_suitcode_tool is None
    assert estimated.token_breakdown.tokens_before_first_suitcode_tool is None
    assert estimated.token_breakdown.first_high_value_suitcode_tool is None
