from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Callable

from suitcode.analytics.inefficiency import InefficiencyDetector
from suitcode.analytics.models import (
    AnalyticsEvent,
    AnalyticsSummary,
    AnalyticsStatus,
    BenchmarkReport,
    InefficiencyFinding,
    ToolUsageStats,
)
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.token_estimation import TokenEstimator


@dataclass(frozen=True)
class _InvocationRecord:
    invocation_id: str
    tool_name: str
    has_started_event: bool
    terminal_event: AnalyticsEvent | None


class AnalyticsAggregator:
    def __init__(
        self,
        store: JsonlAnalyticsStore,
        *,
        tool_catalog: tuple[str, ...],
        excluded_tools: tuple[str, ...] = (),
        estimator: TokenEstimator | None = None,
        detector: InefficiencyDetector | None = None,
    ) -> None:
        self._store = store
        self._tool_catalog = tool_catalog
        self._excluded_tools = excluded_tools
        self._estimator = estimator or TokenEstimator()
        self._detector = detector or InefficiencyDetector(tool_catalog=tool_catalog, excluded_tools=excluded_tools)

    def load_events(
        self,
        *,
        repository_root: Path | None = None,
        include_global: bool = True,
        session_id: str | None = None,
        event_filter: Callable[[AnalyticsEvent], bool] | None = None,
    ) -> tuple[AnalyticsEvent, ...]:
        events = self._store.load_events(repository_root=repository_root, include_global=include_global)
        filtered = tuple(item for item in events if item.tool_name not in self._excluded_tools)
        if session_id is None:
            session_filtered = filtered
        else:
            normalized = session_id.strip()
            if not normalized:
                raise ValueError("session_id must not be empty when provided")
            session_filtered = tuple(item for item in filtered if item.session_id == normalized)
        if event_filter is None:
            return session_filtered
        return tuple(item for item in session_filtered if event_filter(item))

    def summary(
        self,
        *,
        repository_root: Path | None = None,
        include_global: bool = True,
        session_id: str | None = None,
        event_filter: Callable[[AnalyticsEvent], bool] | None = None,
    ) -> AnalyticsSummary:
        events = self.load_events(
            repository_root=repository_root,
            include_global=include_global,
            session_id=session_id,
            event_filter=event_filter,
        )
        invocations = _collapse_invocations(events)
        terminal_events = [item.terminal_event for item in invocations if item.terminal_event is not None]
        durations = [item.duration_ms for item in terminal_events]
        p50, p95 = _latency_percentiles(durations)
        status_counts = Counter(item.status for item in terminal_events)
        payload_bytes = sum(item.output_payload_bytes or 0 for item in terminal_events)
        estimates = [self._estimator.estimate(item) for item in terminal_events]
        confidence_mix = Counter(item.confidence_level.value for item in estimates)
        tool_counts = Counter(item.tool_name for item in invocations)
        return AnalyticsSummary(
            total_calls=len(invocations),
            started_calls=sum(1 for item in invocations if item.has_started_event),
            finished_calls=len(terminal_events),
            unfinished_calls=sum(1 for item in invocations if item.has_started_event and item.terminal_event is None),
            success_calls=status_counts.get(AnalyticsStatus.SUCCESS, 0),
            error_calls=status_counts.get(AnalyticsStatus.ERROR, 0),
            p50_duration_ms=p50,
            p95_duration_ms=p95,
            total_payload_bytes=payload_bytes,
            estimated_tokens=sum(item.actual_tokens_estimate for item in estimates),
            estimated_tokens_saved=sum(item.estimated_tokens_saved for item in estimates),
            confidence_mix=dict(confidence_mix),
            top_tools=tuple(tool for tool, _ in tool_counts.most_common(5)),
        )

    def tool_usage(
        self,
        *,
        repository_root: Path | None = None,
        include_global: bool = True,
        session_id: str | None = None,
        event_filter: Callable[[AnalyticsEvent], bool] | None = None,
    ) -> tuple[ToolUsageStats, ...]:
        events = self.load_events(
            repository_root=repository_root,
            include_global=include_global,
            session_id=session_id,
            event_filter=event_filter,
        )
        by_tool: dict[str, list[_InvocationRecord]] = defaultdict(list)
        for item in _collapse_invocations(events):
            by_tool[item.tool_name].append(item)

        results: list[ToolUsageStats] = []
        for tool_name, group in by_tool.items():
            terminal_events = [item.terminal_event for item in group if item.terminal_event is not None]
            status_counts = Counter(item.status for item in terminal_events)
            durations = [item.duration_ms for item in terminal_events]
            p50, p95 = _latency_percentiles(durations)
            payload_bytes = sum(item.output_payload_bytes or 0 for item in terminal_events)
            estimates = [self._estimator.estimate(item) for item in terminal_events]
            confidence_mix = Counter(item.confidence_level.value for item in estimates)
            results.append(
                ToolUsageStats(
                    tool_name=tool_name,
                    total_calls=len(group),
                    started_calls=sum(1 for item in group if item.has_started_event),
                    finished_calls=len(terminal_events),
                    unfinished_calls=sum(1 for item in group if item.has_started_event and item.terminal_event is None),
                    success_calls=status_counts.get(AnalyticsStatus.SUCCESS, 0),
                    error_calls=status_counts.get(AnalyticsStatus.ERROR, 0),
                    p50_duration_ms=p50,
                    p95_duration_ms=p95,
                    total_payload_bytes=payload_bytes,
                    estimated_tokens=sum(item.actual_tokens_estimate for item in estimates),
                    estimated_tokens_saved=sum(item.estimated_tokens_saved for item in estimates),
                    confidence_mix=dict(confidence_mix),
                )
            )
        return tuple(sorted(results, key=lambda item: (-item.total_calls, item.tool_name)))

    def inefficient_calls(
        self,
        *,
        repository_root: Path | None = None,
        include_global: bool = True,
        session_id: str | None = None,
        event_filter: Callable[[AnalyticsEvent], bool] | None = None,
    ) -> tuple[InefficiencyFinding, ...]:
        events = self.load_events(
            repository_root=repository_root,
            include_global=include_global,
            session_id=session_id,
            event_filter=event_filter,
        )
        return self._detector.detect(events)

    def benchmark_report(self) -> BenchmarkReport | None:
        benchmark_dir = self._store.global_root() / "benchmarks"
        if not benchmark_dir.exists():
            return None
        report_files = tuple(item for item in benchmark_dir.glob("*/report.json") if item.is_file())
        if not report_files:
            report_files = tuple(item for item in benchmark_dir.glob("report-*.json") if item.is_file())
        if not report_files:
            return None
        latest = max(report_files, key=lambda item: item.stat().st_mtime_ns)
        return BenchmarkReport.model_validate_json(latest.read_text(encoding="utf-8"))


def _latency_percentiles(values: list[int]) -> tuple[int, int]:
    if not values:
        return 0, 0
    ordered = sorted(values)
    p50 = int(median(ordered))
    p95_index = int((len(ordered) - 1) * 0.95)
    p95 = ordered[p95_index]
    return p50, p95


def _collapse_invocations(events: tuple[AnalyticsEvent, ...]) -> tuple[_InvocationRecord, ...]:
    grouped: dict[str, list[AnalyticsEvent]] = defaultdict(list)
    for event in events:
        key = event.invocation_id or event.event_id
        grouped[key].append(event)

    invocations: list[_InvocationRecord] = []
    for invocation_id, group in grouped.items():
        ordered = sorted(group, key=lambda item: (item.timestamp_utc, item.event_id))
        terminal_events = [item for item in ordered if item.status.is_terminal]
        terminal_event = terminal_events[-1] if terminal_events else None
        representative = terminal_event or ordered[-1]
        invocations.append(
            _InvocationRecord(
                invocation_id=invocation_id,
                tool_name=representative.tool_name,
                has_started_event=any(item.status == AnalyticsStatus.STARTED for item in ordered),
                terminal_event=terminal_event,
            )
        )
    return tuple(sorted(invocations, key=lambda item: item.invocation_id))
