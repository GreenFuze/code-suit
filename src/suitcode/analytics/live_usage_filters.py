from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from suitcode.analytics.models import AnalyticsEvent
from suitcode.analytics.native_agent_models import NativeSessionAnalytics

_PATH_MARKERS = (
    "/appdata/local/temp/pytest-",
    "\\appdata\\local\\temp\\pytest-",
    "/tmp/pytest-",
    "\\tmp\\pytest-",
    "/pytest-of-",
    "\\pytest-of-",
    "/tests/test_repos/",
    "\\tests\\test_repos\\",
    "/tests/fixtures/",
    "\\tests\\fixtures\\",
)


def parse_cutoff(*, since_utc: str | None, since_hours: int | None) -> datetime | None:
    if since_utc and since_hours is not None:
        raise ValueError("provide only one of --since-utc or --since-hours")
    if since_hours is not None:
        if since_hours <= 0:
            raise ValueError("--since-hours must be > 0")
        return datetime.now(tz=UTC) - timedelta(hours=since_hours)
    if since_utc:
        normalized = since_utc[:-1] + "+00:00" if since_utc.endswith("Z") else since_utc
        return datetime.fromisoformat(normalized).astimezone(UTC)
    return None


def is_generated_path(value: str | Path | None) -> bool:
    if value is None:
        return False
    normalized = str(value).replace("/", "\\").lower()
    return any(marker in normalized for marker in _PATH_MARKERS)


def event_matches_live_filters(
    event: AnalyticsEvent,
    *,
    cutoff: datetime | None,
    exclude_test_artifacts: bool,
    exclude_benchmark_events: bool,
) -> bool:
    if exclude_benchmark_events and event.benchmark_run_id is not None:
        return False
    if cutoff is not None:
        normalized = event.timestamp_utc[:-1] + "+00:00"
        event_time = datetime.fromisoformat(normalized).astimezone(UTC)
        if event_time < cutoff:
            return False
    if not exclude_test_artifacts:
        return True
    if is_generated_path(event.repository_root):
        return False
    for value in event.arguments_redacted.values():
        if isinstance(value, str) and is_generated_path(value):
            return False
    return True


def session_matches_live_filters(
    session: NativeSessionAnalytics,
    *,
    cutoff: datetime | None,
    exclude_test_artifacts: bool,
) -> bool:
    if cutoff is not None and session.artifact.last_event_at < cutoff:
        return False
    if not exclude_test_artifacts:
        return True
    if is_generated_path(session.artifact.artifact_path):
        return False
    if is_generated_path(session.repository_root):
        return False
    if is_generated_path(session.artifact.repository_root):
        return False
    return True
