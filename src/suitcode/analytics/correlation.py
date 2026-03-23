from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from suitcode.analytics.models import AnalyticsEvent
from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.native_agent_models import CorrelationQuality, NativeSessionAnalytics, NativeSuitCodeToolUse
from suitcode.analytics.storage import JsonlAnalyticsStore


class AnalyticsCorrelationService:
    def __init__(self, store: JsonlAnalyticsStore, *, timing_tolerance: timedelta | None = None) -> None:
        self._store = store
        self._timing_tolerance = timing_tolerance or timedelta(minutes=5)
        self._events_cache: dict[tuple[str, bool], tuple[AnalyticsEvent, ...]] = {}

    def correlate_session(self, session: NativeSessionAnalytics, repository_root: Path | None) -> NativeSessionAnalytics:
        if repository_root is None:
            return session.model_copy(update={"correlation_quality": CorrelationQuality.NONE})

        events = self._load_events(repository_root, include_global=True)
        if not events:
            return session.model_copy(
                update={
                    "correlation_quality": CorrelationQuality.NONE,
                    "notes": (*session.notes, "no SuitCode analytics events were found for the repository"),
                }
            )

        matching_session_events = tuple(item for item in events if item.session_id == session.session_id)
        session_tool_names = {tool.tool_name for tool in session.suitcode_tools}
        overlap_tools = {item.tool_name for item in events if item.tool_name in session_tool_names}
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
        elif matching_session_events and time_window_events:
            correlated_events = time_window_events
            correlated_session_id = session.session_id
            quality = CorrelationQuality.STRONG
        elif time_window_events and session.repository_root is not None:
            correlated_events = time_window_events
            quality = CorrelationQuality.STRONG
            counts = Counter(item.session_id for item in time_window_events)
            correlated_session_id = counts.most_common(1)[0][0]
        elif correlated_events and correlated_session_id is None:
            counts = Counter(item.session_id for item in correlated_events)
            correlated_session_id = counts.most_common(1)[0][0]

        if quality == CorrelationQuality.REPO_ONLY:
            notes.append("repository matched but no overlapping SuitCode analytics events were found")
        elif quality == CorrelationQuality.TOOL_OVERLAP and not overlap_and_time:
            notes.append("tool overlap found without timing overlap")

        update: dict[str, object] = {
            "correlation_quality": quality,
            "correlated_analytics_session_id": correlated_session_id,
            "correlated_event_count": len(correlated_events),
            "notes": tuple(notes),
        }
        if not session.suitcode_tools and quality in {
            CorrelationQuality.SESSION_ONLY,
            CorrelationQuality.TOOL_OVERLAP,
            CorrelationQuality.STRONG,
        } and correlated_events:
            synthesized_tools = _tool_usage_from_events(correlated_events)
            first_suitcode_tool = synthesized_tools[0].tool_name if synthesized_tools else None
            first_high_value_suitcode_tool = next(
                (item.tool_name for item in synthesized_tools if item.tool_name in HIGH_VALUE_TOOL_SET),
                None,
            )
            update.update(
                {
                    "used_suitcode": bool(synthesized_tools),
                    "suitcode_tools": synthesized_tools,
                    "first_suitcode_tool": first_suitcode_tool,
                    "first_high_value_suitcode_tool": first_high_value_suitcode_tool,
                    "notes": tuple(
                        [
                            *notes,
                            "SuitCode tool visibility synthesized from correlated MCP analytics events",
                        ]
                    ),
                }
            )

        return session.model_copy(update=update)

    def correlate_codex_session(self, session: NativeSessionAnalytics, repository_root: Path | None) -> NativeSessionAnalytics:
        return self.correlate_session(session, repository_root)

    def _timing_overlap_events(self, session: NativeSessionAnalytics, events: tuple[AnalyticsEvent, ...]) -> tuple[AnalyticsEvent, ...]:
        start = session.artifact.started_at - self._timing_tolerance
        end = session.artifact.last_event_at + self._timing_tolerance
        matched: list[AnalyticsEvent] = []
        for item in events:
            timestamp = _analytics_timestamp(item)
            if start <= timestamp <= end:
                matched.append(item)
        return tuple(matched)

    def _load_events(self, repository_root: Path, *, include_global: bool) -> tuple[AnalyticsEvent, ...]:
        cache_key = (str(repository_root), include_global)
        cached = self._events_cache.get(cache_key)
        if cached is not None:
            return cached
        expected_root = str(repository_root)
        events = tuple(
            item
            for item in self._store.load_events(repository_root=repository_root, include_global=include_global)
            if item.repository_root == expected_root
        )
        self._events_cache[cache_key] = events
        return events


def _analytics_timestamp(event: AnalyticsEvent) -> datetime:
    raw = event.timestamp_utc[:-1] + "+00:00" if event.timestamp_utc.endswith("Z") else event.timestamp_utc
    return datetime.fromisoformat(raw).astimezone(UTC)


def _tool_usage_from_events(events: tuple[AnalyticsEvent, ...]) -> tuple[NativeSuitCodeToolUse, ...]:
    by_name: dict[str, list[datetime]] = {}
    for event in events:
        by_name.setdefault(event.tool_name, []).append(_analytics_timestamp(event))
    ordered: list[NativeSuitCodeToolUse] = []
    for tool_name, timestamps in sorted(by_name.items(), key=lambda item: (min(item[1]), item[0])):
        ordered.append(
            NativeSuitCodeToolUse(
                tool_name=tool_name,
                call_count=len(timestamps),
                first_seen_at=min(timestamps),
                last_seen_at=max(timestamps),
            )
        )
    return tuple(ordered)
