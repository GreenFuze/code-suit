from __future__ import annotations

from pathlib import Path

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore


def _settings(tmp_path: Path) -> AnalyticsSettings:
    return AnalyticsSettings(
        global_root=tmp_path / "global",
        repo_subdir=".suit/analytics",
        max_file_bytes=10 * 1024,
    )


def _event(
    event_id: str,
    tool_name: str,
    *,
    offset: int | None = None,
    session_id: str = "session:x",
    repository_path: str | None = None,
) -> AnalyticsEvent:
    args: dict[str, object] = {"workspace_id": "workspace:x", "repository_id": "repo:x"}
    if offset is not None:
        args["limit"] = 20
        args["offset"] = offset
    if repository_path is not None:
        args["repository_path"] = repository_path
    return AnalyticsEvent(
        event_id=event_id,
        session_id=session_id,
        timestamp_utc=f"2026-03-06T12:00:{int(event_id[-1]):02d}Z",
        tool_name=tool_name,
        workspace_id="workspace:x",
        repository_id="repo:x",
        repository_root="C:/repo",
        arguments_redacted=args,
        arguments_fingerprint_sha256=f"hash-{tool_name}-{offset}-{session_id}",
        status=AnalyticsStatus.SUCCESS,
        duration_ms=10,
        output_model_type="ListResult",
        output_payload_bytes=120,
        output_payload_sha256=f"out-{event_id}",
    )


def test_aggregator_reports_summary_and_tool_usage(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonlAnalyticsStore(settings)
    for item in (
        _event("event:1", "list_components"),
        _event("event:2", "describe_components"),
        _event("event:3", "analyze_change"),
    ):
        store.append_event(item)

    aggregator = AnalyticsAggregator(
        store,
        tool_catalog=("list_components", "describe_components", "analyze_change"),
        excluded_tools=tuple(),
    )
    summary = aggregator.summary()
    usage = aggregator.tool_usage()

    assert summary.total_calls == 3
    assert summary.estimated_tokens > 0
    assert summary.estimated_tokens_saved >= 0
    assert len(usage) == 3
    assert any(item.tool_name == "analyze_change" for item in usage)


def test_aggregator_session_filter_and_include_global_behavior(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonlAnalyticsStore(settings)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    store.append_event(_event("event:1", "list_components", session_id="session:repo"), repository_root=repo_root)
    store.append_event(_event("event:2", "list_components", session_id="session:global"), repository_root=None)

    aggregator = AnalyticsAggregator(
        store,
        tool_catalog=("list_components", "analyze_change"),
        excluded_tools=tuple(),
    )

    repo_local = aggregator.summary(repository_root=repo_root, include_global=False)
    repo_plus_global = aggregator.summary(repository_root=repo_root, include_global=True)
    session_scoped = aggregator.summary(repository_root=repo_root, include_global=True, session_id="session:repo")

    assert repo_local.total_calls == 1
    assert repo_plus_global.total_calls == 2
    assert session_scoped.total_calls == 1


def test_inefficiency_detector_finds_duplicate_pagination_and_workspace_churn(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = JsonlAnalyticsStore(settings)
    store.append_event(_event("event:1", "find_symbols", session_id="session:a"))
    store.append_event(_event("event:2", "find_symbols", session_id="session:a"))
    store.append_event(_event("event:3", "find_symbols", session_id="session:a"))
    store.append_event(_event("event:4", "list_components", offset=0, session_id="session:a"))
    store.append_event(_event("event:5", "list_components", offset=20, session_id="session:a"))
    store.append_event(_event("event:6", "list_components", offset=40, session_id="session:a"))
    store.append_event(_event("event:7", "list_components", offset=60, session_id="session:a"))
    store.append_event(_event("event:8", "open_workspace", session_id="session:a", repository_path="C:/repo"))
    store.append_event(_event("event:9", "open_workspace", session_id="session:a", repository_path="C:/repo"))
    store.append_event(_event("event:0", "open_workspace", session_id="session:a", repository_path="C:/repo"))

    aggregator = AnalyticsAggregator(
        store,
        tool_catalog=("find_symbols", "list_components", "open_workspace", "analyze_change"),
        excluded_tools=tuple(),
    )
    findings = aggregator.inefficient_calls(session_id="session:a")
    kinds = {item.kind for item in findings}

    assert "duplicate_call" in kinds
    assert "pagination_thrash" in kinds
    assert "workspace_churn" in kinds
    churn = next(item for item in findings if item.kind == "workspace_churn")
    assert churn.tool_name == "open_workspace"
    assert churn.session_id == "session:a"
