from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from suitcode.analytics.models import AnalyticsEvent
from suitcode.analytics.native_agent_models import CodexSessionAnalytics, CorrelationQuality
from suitcode.analytics.storage import JsonlAnalyticsStore


class AnalyticsCorrelationService:
    def __init__(self, store: JsonlAnalyticsStore, *, timing_tolerance: timedelta | None = None) -> None:
        self._store = store
        self._timing_tolerance = timing_tolerance or timedelta(minutes=5)

    def correlate_codex_session(self, session: CodexSessionAnalytics, repository_root: Path | None) -> CodexSessionAnalytics:
        if repository_root is None:
            return session.model_copy(update={"correlation_quality": CorrelationQuality.NONE})

        events = self._store.load_events(repository_root=repository_root, include_global=True)
        if not events:
            return session.model_copy(
                update={
                    "correlation_quality": CorrelationQuality.NONE,
                    "notes": (*session.notes, "no SuitCode analytics events were found for the repository"),
                }
            )

        matching_session_events = tuple(item for item in events if item.session_id == session.session_id)
        overlap_tools = {
            item.tool_name
            for item in events
            if item.tool_name in {tool.tool_name for tool in session.suitcode_tools}
        }
        time_window_events = self._timing_overlap_events(session, events)
        overlap_and_time = tuple(item for item in time_window_events if item.tool_name in overlap_tools)

        quality = CorrelationQuality.REPO_ONLY
        correlated_events: tuple[AnalyticsEvent, ...] = ()
        correlated_session_id: str | None = None
        notes = list(session.notes)

        if matching_session_events:
            correlated_events = matching_session_events
            correlated_session_id = session.session_id
            quality = CorrelationQuality.SESSION_ONLY

        if overlap_tools:
            correlated_events = tuple(item for item in events if item.tool_name in overlap_tools)
            quality = CorrelationQuality.TOOL_OVERLAP

        if matching_session_events and overlap_and_time:
            correlated_events = overlap_and_time
            correlated_session_id = session.session_id
            quality = CorrelationQuality.STRONG
        elif overlap_and_time:
            correlated_events = overlap_and_time
            quality = CorrelationQuality.STRONG
            counts = Counter(item.session_id for item in overlap_and_time)
            correlated_session_id = counts.most_common(1)[0][0]
        elif correlated_events and correlated_session_id is None:
            counts = Counter(item.session_id for item in correlated_events)
            correlated_session_id = counts.most_common(1)[0][0]

        if quality == CorrelationQuality.REPO_ONLY:
            notes.append("repository matched but no overlapping SuitCode analytics events were found")
        elif quality == CorrelationQuality.TOOL_OVERLAP and not overlap_and_time:
            notes.append("tool overlap found without timing overlap")

        return session.model_copy(
            update={
                "correlation_quality": quality,
                "correlated_analytics_session_id": correlated_session_id,
                "correlated_event_count": len(correlated_events),
                "notes": tuple(notes),
            }
        )

    def _timing_overlap_events(self, session: CodexSessionAnalytics, events: tuple[AnalyticsEvent, ...]) -> tuple[AnalyticsEvent, ...]:
        start = session.artifact.started_at - self._timing_tolerance
        end = session.artifact.last_event_at + self._timing_tolerance
        matched: list[AnalyticsEvent] = []
        for item in events:
            timestamp = _analytics_timestamp(item)
            if start <= timestamp <= end:
                matched.append(item)
        return tuple(matched)


def _analytics_timestamp(event: AnalyticsEvent) -> datetime:
    raw = event.timestamp_utc[:-1] + "+00:00" if event.timestamp_utc.endswith("Z") else event.timestamp_utc
    return datetime.fromisoformat(raw).astimezone(UTC)
