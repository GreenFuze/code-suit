from __future__ import annotations

import json
import sys
from pathlib import Path

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus, AnalyticsSummary, InefficiencyFinding, ToolUsageStats

from scripts import analyze_analytics


class _FakeStore:
    def __init__(self, settings) -> None:
        self._events = (
            AnalyticsEvent(
                event_id="event-1",
                session_id="session-1",
                timestamp_utc="2026-03-22T12:00:00Z",
                tool_name="repository_summary_by_path",
                repository_root="C:/repo",
                arguments_redacted={"repository_path": "C:/repo"},
                arguments_fingerprint_sha256="a" * 64,
                status=AnalyticsStatus.SUCCESS,
                duration_ms=25,
            ),
            AnalyticsEvent(
                event_id="event-2",
                session_id="session-1",
                timestamp_utc="2026-03-22T12:01:00Z",
                tool_name="get_minimum_verified_change_set_by_path",
                repository_root="C:/repo",
                arguments_redacted={"repository_rel_path": "server/main.go"},
                arguments_fingerprint_sha256="b" * 64,
                status=AnalyticsStatus.ERROR,
                error_class="McpValidationError",
                error_message="no deterministic validation surfaces were found",
                duration_ms=41,
            ),
        )

    def load_events(self, repository_root=None, include_global=False):
        return self._events


class _FakeAggregator:
    def __init__(self, store, tool_catalog, excluded_tools) -> None:
        pass

    def summary(self, repository_root=None, include_global=False, session_id=None, event_filter=None):
        return AnalyticsSummary(
            total_calls=2,
            started_calls=0,
            finished_calls=2,
            unfinished_calls=0,
            success_calls=1,
            error_calls=1,
            p50_duration_ms=25,
            p95_duration_ms=41,
            total_payload_bytes=0,
            estimated_tokens=10,
            estimated_tokens_saved=5,
            confidence_mix={"high": 1, "low": 1},
            top_tools=("get_minimum_verified_change_set_by_path", "repository_summary_by_path"),
        )

    def tool_usage(self, repository_root=None, include_global=False, session_id=None, event_filter=None):
        return (
            ToolUsageStats(
                tool_name="get_minimum_verified_change_set_by_path",
                total_calls=1,
                started_calls=0,
                finished_calls=1,
                unfinished_calls=0,
                success_calls=0,
                error_calls=1,
                p50_duration_ms=41,
                p95_duration_ms=41,
                total_payload_bytes=0,
                estimated_tokens=5,
                estimated_tokens_saved=0,
                confidence_mix={"low": 1},
            ),
        )

    def inefficient_calls(self, repository_root=None, include_global=False, session_id=None, event_filter=None):
        return (
            InefficiencyFinding(
                kind="unused_tool",
                tool_name="analyze_change",
                session_id="session-1",
                count=0,
                description="unused",
            ),
        )


def test_script_outputs_detailed_events_json(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(analyze_analytics, "JsonlAnalyticsStore", _FakeStore)
    monkeypatch.setattr(analyze_analytics, "AnalyticsAggregator", _FakeAggregator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_analytics",
            "--repository-root",
            str(tmp_path),
            "--tool-name",
            "get_minimum_verified_change_set_by_path",
            "--include-events",
            "--event-limit",
            "10",
            "--json",
        ],
    )

    analyze_analytics.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["filters"]["tool_name"] == "get_minimum_verified_change_set_by_path"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["tool_name"] == "get_minimum_verified_change_set_by_path"
    assert payload["events"][0]["error_class"] == "McpValidationError"


def test_script_filters_benchmark_and_test_events(monkeypatch, capsys, tmp_path) -> None:
    class _MixedStore(_FakeStore):
        def __init__(self, settings) -> None:
            super().__init__(settings)
            self._events = self._events + (
                AnalyticsEvent(
                    event_id="event-3",
                    session_id="session-2",
                    benchmark_run_id="benchmark-1",
                    benchmark_task_id="task-1",
                    timestamp_utc="2026-03-22T13:00:00Z",
                    tool_name="repository_summary_by_path",
                    repository_root=str(Path.home() / "AppData" / "Local" / "Temp" / "pytest-of-user" / "repo"),
                    arguments_redacted={"repository_path": str(tmp_path / "tests" / "test_repos" / "npm")},
                    arguments_fingerprint_sha256="c" * 64,
                    status=AnalyticsStatus.SUCCESS,
                    duration_ms=15,
                ),
            )

    monkeypatch.setattr(analyze_analytics, "JsonlAnalyticsStore", _MixedStore)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_analytics",
            "--repository-root",
            str(tmp_path),
            "--include-events",
            "--exclude-test-artifacts",
            "--exclude-benchmark-events",
            "--json",
        ],
    )

    analyze_analytics.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["filters"]["exclude_test_artifacts"] is True
    assert payload["filters"]["exclude_benchmark_events"] is True
    assert len(payload["events"]) == 2
