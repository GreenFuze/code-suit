from __future__ import annotations

import json
from pathlib import Path

from suitcode.analytics.token_economics import (
    TokenCounter,
    TokenEconomicsRecorder,
    TokenEconomicsStore,
    generate_token_economics_report,
)
from suitcode.analytics.token_economics_cli import main as token_economics_main


class _WhitespaceTokenCounter(TokenCounter):
    def __init__(self) -> None:
        self.name = "test_whitespace"
        self.version = "test"

    def count_text(self, text: str) -> int:
        return len(text.split())


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
