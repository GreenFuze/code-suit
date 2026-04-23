from __future__ import annotations

from pathlib import Path

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore


def _settings(tmp_path: Path, max_file_bytes: int = 10 * 1024) -> AnalyticsSettings:
    return AnalyticsSettings(
        global_root=tmp_path / "global",
        repo_subdir=".suit/analytics",
        max_file_bytes=max_file_bytes,
    )


def test_recorder_writes_timestamp_and_redacts_sensitive_arguments(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)

    recorder.record_success(
        invocation_id=None,
        tool_name="open_workspace",
        arguments={"repository_path": "C:/repo", "api_token": "secret-value"},
        repository_root=None,
        result={"ok": True},
        duration_ms=7,
    )

    events = store.load_events(include_global=True)
    assert len(events) == 1
    event = events[0]
    assert event.timestamp_utc.endswith("Z")
    assert event.arguments_redacted["api_token"] == "<redacted>"
    assert event.status == AnalyticsStatus.SUCCESS


def test_recorder_applies_and_clears_benchmark_context(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)

    with recorder.benchmark_context(run_id="benchmark-1", task_id="task-1"):
        recorder.record_success(
            invocation_id=None,
            tool_name="repository_summary",
            arguments={"workspace_id": "workspace:test", "repository_id": "repo:test"},
            repository_root=None,
            result={"ok": True},
            duration_ms=5,
        )

    recorder.record_success(
        invocation_id=None,
        tool_name="list_components",
        arguments={"workspace_id": "workspace:test", "repository_id": "repo:test"},
        repository_root=None,
        result={"ok": True},
        duration_ms=3,
    )

    events = store.load_events(include_global=True)
    assert events[0].benchmark_run_id == "benchmark-1"
    assert events[0].benchmark_task_id == "task-1"
    assert events[1].benchmark_run_id is None
    assert events[1].benchmark_task_id is None


def test_recorder_rejects_empty_benchmark_context_values(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)

    try:
        recorder.set_benchmark_context(run_id="", task_id="task-1")
        assert False, "expected ValueError for empty run_id"
    except ValueError as exc:
        assert "must not be empty" in str(exc)


def test_storage_rollover_is_size_based(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path, max_file_bytes=1024))
    recorder = ToolCallRecorder(store)

    for index in range(12):
        recorder.record_success(
            invocation_id=None,
            tool_name="list_supported_providers",
            arguments={"index": index, "payload": "x" * 700},
            repository_root=None,
            result={"result": "ok"},
            duration_ms=1,
        )

    events_dir = store.global_root() / "events"
    archived = tuple(events_dir.glob("events-*.jsonl"))
    assert archived
    assert (events_dir / "active.jsonl").exists()


def test_recorder_writes_started_event_with_shared_invocation_id(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)

    recorder.record_started(
        invocation_id="call:123",
        tool_name="understand_file",
        arguments={"repository_path": "C:/repo"},
        repository_root=None,
    )
    recorder.record_success(
        invocation_id="call:123",
        tool_name="understand_file",
        arguments={"repository_path": "C:/repo"},
        repository_root=None,
        result={"ok": True},
        duration_ms=9,
    )

    events = store.load_events(include_global=True)
    assert len(events) == 2
    assert events[0].status == AnalyticsStatus.STARTED
    assert events[1].status == AnalyticsStatus.SUCCESS
    assert events[0].invocation_id == "call:123"
    assert events[1].invocation_id == "call:123"


def test_recorder_flushes_interrupted_started_calls(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)

    recorder.record_started(
        invocation_id="call:interrupted",
        tool_name="understand_file",
        arguments={"repository_path": str(repository_root), "repository_rel_paths": ("src/index.ts",)},
        repository_root=repository_root,
        started_at_epoch_seconds=1_700_000_000.0,
        started_perf_counter=10.0,
    )
    recorder.flush_interrupted_calls(reason="normal shutdown")

    events = store.load_events(repository_root=repository_root, include_global=False)
    assert len(events) == 2
    assert events[0].status == AnalyticsStatus.STARTED
    assert events[1].status == AnalyticsStatus.INTERRUPTED
    assert events[1].invocation_id == "call:interrupted"
    assert events[1].error_class == "InterruptedToolCall"
