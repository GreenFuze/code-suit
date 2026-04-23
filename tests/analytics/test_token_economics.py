from __future__ import annotations

import json
from pathlib import Path

from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.token_economics import (
    TokenCounter,
    TokenEconomicsRecorder,
    TokenEconomicsRunManifest,
    TokenEconomicsStore,
    generate_token_economics_report,
    write_token_economics_report_artifacts,
)
from suitcode.analytics.token_economics_cli import main as token_economics_main


class _WhitespaceTokenCounter(TokenCounter):
    def __init__(self) -> None:
        self.name = "test_whitespace"
        self.version = "test"

    def count_text(self, text: str) -> int:
        return len(text.split())


def _analytics_settings(tmp_path: Path) -> AnalyticsSettings:
    return AnalyticsSettings(
        global_root=tmp_path / "global",
        repo_subdir=".suit/analytics",
        max_file_bytes=10 * 1024,
    )


def _write_codex_transcript(path: Path, *, cwd: Path) -> None:
    lines = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-session:test",
                "cwd": str(cwd),
                "timestamp": "2024-01-01T00:00:00Z",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2024-01-01T00:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the repo and explain the risky areas."}],
            },
        },
        {
            "timestamp": "2024-01-01T00:00:10Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "mcp__suitcode__understand_repository",
                "call_id": "call-1",
                "arguments": {"repository_path": str(cwd)},
            },
        },
        {
            "timestamp": "2024-01-01T00:00:12Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": {"component_count": 1, "test_count": 1},
            },
        },
        {
            "timestamp": "2024-01-01T00:00:20Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Repository summary captured."}],
            },
        },
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _write_codex_transcript_with_multiple_session_meta(path: Path, *, initial_cwd: Path, final_cwd: Path) -> None:
    lines = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-session:parent",
                "cwd": str(initial_cwd),
                "timestamp": "2024-01-01T00:00:00Z",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2024-01-01T00:00:01Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-session:child",
                "cwd": str(final_cwd),
                "timestamp": "2024-01-01T00:00:01Z",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2024-01-01T00:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the repo and explain the risky areas."}],
            },
        },
        {
            "timestamp": "2024-01-01T00:00:10Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "mcp__suitcode__understand_repository",
                "call_id": "call-1",
                "arguments": {"repository_path": str(final_cwd)},
            },
        },
        {
            "timestamp": "2024-01-01T00:00:12Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": {"component_count": 1, "test_count": 1},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def test_token_economics_recorder_writes_success_and_dedupes_session_evidence(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma delta\nsecond line\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    result = {
        "detail_level": "standard",
        "targets": [
            {
                "repository_rel_path": "src/index.ts",
                "reference_sites_preview": [
                    {
                        "path": "src/index.ts",
                        "span": "src/index.ts:1",
                        "provenance": [
                            {
                                "confidence_mode": "authoritative",
                                "source_kind": "lsp",
                                "source_tool": "typescript-language-server",
                                "evidence_paths": ["src/index.ts"],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    first = recorder.record_success(
        repository_root=repository_root,
        session_id="session:one",
        task_id=None,
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result=result,
        started_at=1_700_000_000.0,
        duration_ms=25,
    )
    second = recorder.record_success(
        repository_root=repository_root,
        session_id="session:one",
        task_id=None,
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result=result,
        started_at=1_700_000_001.0,
        duration_ms=25,
    )

    assert first is not None
    assert second is not None
    assert first.status == "success"
    assert first.evidence_footprint_tokens > 0
    assert first.unique_session_evidence_tokens == first.evidence_footprint_tokens
    assert second.unique_session_evidence_tokens == 0
    assert second.duplicate_session_evidence_tokens == second.evidence_footprint_tokens
    events = TokenEconomicsStore(repository_root).load_events()
    assert len(events) == 2
    report = generate_token_economics_report(repository_root)
    assert report.total.total_elapsed_ms == 50
    assert report.total.avg_elapsed_ms == 25.0
    assert report.total.p50_elapsed_ms == 25
    assert report.total.p95_elapsed_ms == 25
    assert report.total.max_elapsed_ms == 25
    assert report.by_tool[0].name == "understand_file"
    assert report.by_tool[0].avg_elapsed_ms == 25.0


def test_token_economics_recorder_writes_filterable_failures(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())

    event = recorder.record_error(
        repository_root=repository_root,
        session_id="session:failed",
        task_id=None,
        tool_name="what_should_i_run",
        arguments={"repository_path": str(repository_root), "repository_rel_paths": ("plugins/foo/plugin.json",)},
        error=ValueError("unsupported plugin JSON"),
        started_at=1_700_000_000.0,
        duration_ms=10,
    )

    assert event is not None
    assert event.status == "error"
    assert event.error_class == "ValueError"
    success_only = generate_token_economics_report(repository_root)
    with_failures = generate_token_economics_report(repository_root, include_failures=True)
    outside_window = generate_token_economics_report(repository_root, include_failures=True, since="2024-01-01")
    assert success_only.total.event_count == 0
    assert success_only.ignored_event_count == 1
    assert with_failures.total.event_count == 1
    assert with_failures.total.failure_count == 1
    assert outside_window.total.event_count == 0


def test_token_economics_report_supports_ignore_file(tmp_path: Path, capsys) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    event = recorder.record_success(
        repository_root=repository_root,
        session_id="session:ignore-me",
        task_id=None,
        tool_name="understand_file",
        arguments={"repository_path": str(repository_root), "repository_rel_paths": ("src/index.ts",)},
        result={"targets": [{"repository_rel_path": "src/index.ts"}]},
        started_at=1_700_000_000.0,
        duration_ms=10,
    )
    assert event is not None
    ignore_file = repository_root / ".suit" / "analytics" / "token-economics" / "ignore.json"
    ignore_file.write_text(json.dumps({"session_ids": ["session:ignore-me"]}), encoding="utf-8")

    token_economics_main([str(repository_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["ignored_event_count"] == 1
    assert payload["total"]["event_count"] == 0


def test_token_economics_recorder_persists_timing_and_report_surfaces_slow_sections(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "slow.ts").write_text("alpha beta gamma delta\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())

    event = recorder.record_success(
        repository_root=repository_root,
        session_id="session:timing",
        task_id="task:timing",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/slow.ts",),
            "detail_level": "standard",
        },
        result={
            "targets": [{"repository_rel_path": "src/slow.ts"}],
            "timing": {
                "elapsed_ms": 321,
                "repository_reused": False,
                "stages": [
                    {"name": "repository_acquire", "elapsed_ms": 10},
                    {"name": "implementation_flow_summary", "elapsed_ms": 210},
                ],
                "slow_targets": [
                    {
                        "repository_rel_path": "src/slow.ts",
                        "elapsed_ms": 210,
                        "status": "completed",
                        "dominant_stage": "implementation_flow_summary",
                    }
                ],
                "truncated_stage_count": 0,
                "truncated_target_count": 0,
            },
        },
        started_at=1_700_000_000.0,
        duration_ms=321,
    )

    assert event is not None
    assert event.timing is not None
    assert event.timing.elapsed_ms == 321
    report = generate_token_economics_report(repository_root)
    assert report.slowest_calls[0].tool_name == "understand_file"
    assert report.slowest_calls[0].dominant_stage == "implementation_flow_summary"
    assert report.slowest_targets[0].repository_rel_path == "src/slow.ts"
    assert report.dominant_stage_counts["implementation_flow_summary"] == 1


def test_token_economics_report_correlates_codex_transcript_and_computes_task_estimate(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma delta\nsecond line\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    transcript_path = tmp_path / "codex-session.jsonl"
    _write_codex_transcript(transcript_path, cwd=repository_root)

    recorder.record_success(
        repository_root=repository_root,
        session_id="session:task",
        task_id="task:discovery",
        task_kind="discovery",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result={"targets": [{"repository_rel_path": "src/index.ts", "path": "src/index.ts", "span": "src/index.ts:1"}]},
        started_at=1_704_067_210.0,
        duration_ms=25,
    )
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:other",
        task_id="task:other",
        task_kind="discovery",
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        result={"repository": {"component_count": 1}},
        started_at=1_704_068_000.0,
        duration_ms=10,
    )

    report = generate_token_economics_report(
        repository_root,
        codex_transcript_path=transcript_path,
        task_id="task:discovery",
        transcript_window_padding_seconds=30,
    )

    assert report.total.event_count == 1
    assert report.total.correlation_mode == "transcript_window_and_task_id"
    assert report.total.transcript_session_id == "codex-session:test"
    assert report.total.transcript_total_tokens is not None
    assert report.total.transcript_suitcode_tokens is not None
    assert report.total.transcript_non_suitcode_tokens is not None
    assert report.total.estimated_with_suitcode_task_tokens is not None
    assert report.total.estimated_without_suitcode_task_tokens is not None
    assert report.total.estimated_task_token_reduction_pct is not None
    assert report.total.suitcode_evidence_expansion_factor is not None


def test_tool_call_recorder_uses_env_task_metadata_for_token_economics(tmp_path: Path, monkeypatch) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    monkeypatch.setenv("SUITCODE_TASK_ID", "task:env")
    monkeypatch.setenv("SUITCODE_TASK_KIND", "discovery")
    monkeypatch.setenv("SUITCODE_STUDY_KIND", "live_session")
    store = JsonlAnalyticsStore(_analytics_settings(tmp_path))
    recorder = ToolCallRecorder(store, session_id="session:test")

    recorder.record_success(
        invocation_id=None,
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        repository_root=repository_root,
        result={"timing": {"elapsed_ms": 5, "stages": [], "slow_targets": []}},
        duration_ms=5,
        started_at_epoch_seconds=1_700_000_000.0,
    )

    events = TokenEconomicsStore(repository_root).load_events()
    assert len(events) == 1
    assert events[0].task_id == "task:env"
    assert events[0].task_kind == "discovery"
    assert events[0].study_kind == "live_session"


def test_token_economics_recorder_persists_manifest_and_run_metadata(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    recorder = TokenEconomicsRecorder(
        counter=_WhitespaceTokenCounter(),
        analytics_run_id="run:test",
        public_tool_profile="catalog:test",
        workspace_mode="read_only",
        experiment_id="exp-1",
        experiment_label="baseline",
        model_name="gpt-test",
    )

    recorder.record_success(
        repository_root=repository_root,
        session_id="session:manifest",
        task_id="task:manifest",
        task_kind="discovery",
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        result={"repository": {"component_count": 2, "file_count": 5}},
        started_at=1_700_000_000.0,
        duration_ms=11,
    )

    manifests_root = repository_root / ".suit" / "analytics" / "token-economics" / "manifests"
    manifest_path = manifests_root / "run:test.json"
    assert manifest_path.exists()
    manifest = TokenEconomicsRunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.analytics_run_id == "run:test"
    assert manifest.public_tool_profile == "catalog:test"
    assert manifest.workspace_mode == "read_only"
    assert manifest.experiment_id == "exp-1"
    assert manifest.experiment_label == "baseline"
    assert manifest.model_name == "gpt-test"

    event = TokenEconomicsStore(repository_root).load_events()[0]
    assert event.analytics_run_id == "run:test"
    assert event.repository_component_count == 2
    assert event.repository_file_count == 5


def test_token_economics_report_counts_unfinished_calls_from_started_analytics(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    settings = _analytics_settings(tmp_path)
    store = JsonlAnalyticsStore(settings)
    recorder = ToolCallRecorder(store, session_id="session:unfinished", public_tool_profile="catalog:test")

    recorder.record_started(
        invocation_id="call:unfinished",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/missing.ts",),
            "detail_level": "standard",
        },
        repository_root=repository_root,
    )

    report = generate_token_economics_report(repository_root)
    assert report.total.event_count == 0
    assert report.total.unfinished_count == 1
    assert report.by_session[0].name == "session:unfinished"
    assert report.by_session[0].unfinished_count == 1
    assert report.by_tool[0].name == "understand_file"
    assert report.by_tool[0].unfinished_count == 1


def test_token_economics_report_counts_interrupted_terminal_calls(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    settings = _analytics_settings(tmp_path)
    store = JsonlAnalyticsStore(settings)
    recorder = ToolCallRecorder(store, session_id="session:interrupted", public_tool_profile="catalog:test")

    recorder.record_started(
        invocation_id="call:interrupted",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/missing.ts",),
            "detail_level": "standard",
        },
        repository_root=repository_root,
        started_at_epoch_seconds=1_700_000_000.0,
        started_perf_counter=10.0,
    )
    recorder.flush_interrupted_calls(reason="normal shutdown")

    report = generate_token_economics_report(repository_root, include_failures=True)
    assert report.total.event_count == 1
    assert report.total.failure_count == 1
    assert report.total.interrupted_count == 1
    assert report.total.unfinished_count == 0
    assert report.total.status_counts["interrupted"] == 1


def test_token_economics_can_write_json_and_markdown_artifacts(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())

    recorder.record_success(
        repository_root=repository_root,
        session_id="session:artifact",
        task_id="task:artifact",
        task_kind="discovery",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "compact",
        },
        result={"targets": [{"repository_rel_path": "src/index.ts", "path": "src/index.ts", "span": "src/index.ts:1"}]},
        started_at=1_700_000_000.0,
        duration_ms=15,
    )

    report = generate_token_economics_report(repository_root)
    artifacts = write_token_economics_report_artifacts(repository_root, report)

    assert Path(artifacts.json_path).exists()
    assert Path(artifacts.markdown_path).exists()
    markdown = Path(artifacts.markdown_path).read_text(encoding="utf-8")
    assert "SuitCode Token Economics Lab Report" in markdown
    assert "Primary Outcomes" in markdown
    assert "Paper-Readiness Summary" in markdown


def test_token_economics_report_supports_transcript_plus_analytics_session_filter(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma delta\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    transcript_path = tmp_path / "codex-session.jsonl"
    _write_codex_transcript(transcript_path, cwd=repository_root)

    recorder.record_success(
        repository_root=repository_root,
        session_id="session:keep",
        task_id=None,
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result={"targets": [{"repository_rel_path": "src/index.ts"}]},
        started_at=1_704_067_210.0,
        duration_ms=15,
    )
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:drop",
        task_id=None,
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result={"targets": [{"repository_rel_path": "src/index.ts"}]},
        started_at=1_704_067_215.0,
        duration_ms=20,
    )

    report = generate_token_economics_report(
        repository_root,
        codex_transcript_path=transcript_path,
        analytics_session_id="session:keep",
        transcript_window_padding_seconds=30,
    )

    assert report.total.event_count == 1
    assert report.total.correlation_mode == "transcript_window_and_analytics_session_id"


def test_token_economics_cli_supports_transcript_correlation_flags(tmp_path: Path, capsys) -> None:
    repository_root = tmp_path / "repo"
    source = repository_root / "src"
    source.mkdir(parents=True)
    (source / "index.ts").write_text("alpha beta gamma delta\n", encoding="utf-8")
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    transcript_path = tmp_path / "codex-session.jsonl"
    _write_codex_transcript(transcript_path, cwd=repository_root)

    recorder.record_success(
        repository_root=repository_root,
        session_id="session:cli",
        task_id="task:cli",
        task_kind="discovery",
        tool_name="understand_file",
        arguments={
            "repository_path": str(repository_root),
            "repository_rel_paths": ("src/index.ts",),
            "detail_level": "standard",
        },
        result={"targets": [{"repository_rel_path": "src/index.ts"}]},
        started_at=1_704_067_210.0,
        duration_ms=15,
    )

    token_economics_main(
        [
            str(repository_root),
            "--json",
            "--codex-transcript",
            str(transcript_path),
            "--task-id",
            "task:cli",
            "--transcript-window-padding-seconds",
            "30",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["total"]["correlation_mode"] == "transcript_window_and_task_id"
    assert payload["total"]["transcript_session_id"] == "codex-session:test"
    assert payload["total"]["estimated_task_token_reduction_pct"] is not None


def test_token_economics_cli_supports_structured_ignore_exclusions(tmp_path: Path, capsys) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter(), analytics_run_id="run:ignore")
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:ignore",
        task_id="task:ignore",
        task_kind="discovery",
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        result={"repository": {"component_count": 1, "file_count": 1}},
        started_at=1_700_000_000.0,
        duration_ms=15,
    )
    ignore_file = repository_root / ".suit" / "analytics" / "token-economics" / "ignore.json"
    ignore_file.parent.mkdir(parents=True, exist_ok=True)
    ignore_file.write_text(
        json.dumps(
            {
                "exclusions": [
                    {
                        "kind": "analytics_run_id",
                        "value": "run:ignore",
                        "reason": "known_bad_session",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    token_economics_main([str(repository_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["total"]["event_count"] == 0
    assert payload["filters"]["ignored_analytics_run_ids"] == ["run:ignore"]
    assert payload["filters"]["ignore_reason_labels"] == ["known_bad_session"]


def test_token_economics_report_correlates_multi_session_meta_transcript_without_manual_filtering(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()
    transcript_path = tmp_path / "codex-multi-session.jsonl"
    parent_root = (tmp_path / "parent").resolve()
    parent_root.mkdir()
    _write_codex_transcript_with_multiple_session_meta(
        transcript_path,
        initial_cwd=parent_root,
        final_cwd=repository_root,
    )
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter())
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:multi-meta",
        task_id="task:multi-meta",
        task_kind="discovery",
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        result={"repository": {"component_count": 1, "file_count": 1}},
        started_at=1_704_067_210.0,
        duration_ms=15,
    )

    report = generate_token_economics_report(
        repository_root,
        codex_transcript_path=transcript_path,
        transcript_window_padding_seconds=30,
    )

    assert report.total.transcript_session_id == "codex-session:child"
    assert report.total.transcript_total_tokens is not None
    assert report.total.transcript_coverage_partial is False
    assert any("multiple session metadata snapshots" in note for note in report.interpretation_notes)


def test_token_economics_report_groups_by_task_and_study_kind(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    recorder = TokenEconomicsRecorder(counter=_WhitespaceTokenCounter(), analytics_run_id="run:live")
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:one",
        task_id="task:one",
        task_kind="discovery",
        study_kind="live_session",
        tool_name="understand_repository",
        arguments={"repository_path": str(repository_root)},
        result={"repository": {"component_count": 1, "file_count": 1}},
        started_at=1_700_000_000.0,
        duration_ms=10,
    )
    recorder.record_success(
        repository_root=repository_root,
        session_id="session:two",
        task_id="task:two",
        task_kind="validation",
        study_kind="controlled_task",
        tool_name="what_is_not_proven",
        arguments={"repository_path": str(repository_root), "repository_rel_paths": ("src/app.ts",)},
        result={
            "target_count": 1,
            "targets": [],
            "highest_priority_targets": [],
            "shared_gap_codes": [],
            "nearby_validation_surfaces": [],
        },
        started_at=1_700_000_100.0,
        duration_ms=12,
    )

    report = generate_token_economics_report(repository_root, include_failures=True)

    assert {item.name for item in report.by_task_kind} == {"discovery", "validation"}
    assert {item.name for item in report.by_study_kind} == {"controlled_task", "live_session"}
