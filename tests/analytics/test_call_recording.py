from __future__ import annotations

from pathlib import Path

from suitcode.analytics.call_recording import RecordedCallExecutor
from suitcode.analytics.models import AnalyticsStatus
from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore


def _settings(tmp_path: Path) -> AnalyticsSettings:
    return AnalyticsSettings(
        global_root=tmp_path / "global",
        repo_subdir=".suit/analytics",
        max_file_bytes=10 * 1024,
    )


def test_recorded_executor_emits_started_and_success_with_same_invocation_id(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)
    executor = RecordedCallExecutor(
        recorder,
        repository_root_resolver=lambda tool_name, arguments: None,
    )

    result = executor.execute(
        tool_name="understand_repository",
        callable_obj=lambda repository_path: {"ok": repository_path},
        args=(),
        kwargs={"repository_path": "C:/repo"},
    )

    assert result == {"ok": "C:/repo"}
    events = store.load_events(include_global=True)
    assert len(events) == 2
    assert events[0].status == AnalyticsStatus.STARTED
    assert events[1].status == AnalyticsStatus.SUCCESS
    assert events[0].invocation_id is not None
    assert events[0].invocation_id == events[1].invocation_id


def test_recorded_executor_emits_started_and_error_with_same_invocation_id(tmp_path: Path) -> None:
    store = JsonlAnalyticsStore(_settings(tmp_path))
    recorder = ToolCallRecorder(store)
    executor = RecordedCallExecutor(
        recorder,
        repository_root_resolver=lambda tool_name, arguments: None,
    )

    def _boom(repository_path: str) -> object:
        raise RuntimeError(f"failed for {repository_path}")

    try:
        executor.execute(
            tool_name="understand_file",
            callable_obj=_boom,
            args=(),
            kwargs={"repository_path": "C:/repo"},
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass

    events = store.load_events(include_global=True)
    assert len(events) == 2
    assert events[0].status == AnalyticsStatus.STARTED
    assert events[1].status == AnalyticsStatus.ERROR
    assert events[0].invocation_id is not None
    assert events[0].invocation_id == events[1].invocation_id
