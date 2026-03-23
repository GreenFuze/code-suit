from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from suitcode.analytics.native_agent_models import (
    NativeRepositoryAnalyticsSummary,
    NativeSessionAnalytics,
    NativeSuitCodeToolUse,
    NativeTranscriptMetrics,
)
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


class NativeAnalyticsService:
    def __init__(
        self,
        store: Any,
        *,
        parser: Any,
        correlation_service: Any | None = None,
        capture_builder: Any | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
        usage_policy: Any | None = None,
    ) -> None:
        self._store = store
        self._parser = parser
        self._correlation_service = correlation_service
        self._capture_builder = capture_builder
        self._token_estimator = token_estimator
        self._usage_policy = usage_policy
        self._scan_cache: dict[tuple[str | None, str | None], tuple[tuple[NativeSessionAnalytics, ...], int, tuple[str, ...]]] = {}

    def session_analytics(
        self,
        repository_root: Path | None = None,
        session_id: str | None = None,
    ) -> tuple[NativeSessionAnalytics, ...]:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        sessions, _, _ = self._scan_sessions(normalized_root, session_id=session_id)
        return sessions

    def repository_summary(self, repository_root: Path | None = None) -> NativeRepositoryAnalyticsSummary:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        sessions, skipped, notes = self._scan_sessions(normalized_root)
        return self._build_summary(list(sessions), repository_root=normalized_root, skipped=skipped, notes=notes)

    def latest_repository_session(self, repository_root: Path) -> NativeSessionAnalytics | None:
        normalized_root = repository_root.expanduser().resolve()
        sessions, _, _ = self._scan_sessions(normalized_root)
        if not sessions:
            return None
        return sessions[0]

    def _correlate(self, session: NativeSessionAnalytics, repository_root: Path | None) -> NativeSessionAnalytics:
        if self._correlation_service is None:
            return session
        return self._correlation_service.correlate_session(session, repository_root)

    def _enrich(self, session: NativeSessionAnalytics, *, path: Path, repository_root: Path | None) -> NativeSessionAnalytics:
        enriched = self._correlate(session, repository_root)
        if self._capture_builder is not None:
            enriched = enriched.model_copy(update={"transcript_capture": self._capture_builder.build(path)})
        if self._token_estimator is not None and enriched.transcript_capture is not None:
            enriched = self._token_estimator.estimate_session(enriched)
        if self._usage_policy is not None:
            enriched = self._usage_policy(enriched)
        return enriched

    def _scan_sessions(
        self,
        repository_root: Path | None,
        session_id: str | None = None,
    ) -> tuple[tuple[NativeSessionAnalytics, ...], int, tuple[str, ...]]:
        cache_key = (str(repository_root) if repository_root is not None else None, session_id)
        cached = self._scan_cache.get(cache_key)
        if cached is not None:
            return cached

        parsed: list[NativeSessionAnalytics] = []
        skipped = 0
        notes: list[str] = []
        sessions = self._store.list_sessions(repository_root=repository_root, session_id=session_id)
        for path in sessions:
            try:
                item = self._parser.parse(path)
            except ValueError as exc:
                skipped += 1
                notes.append(str(exc))
                continue
            parsed.append(self._enrich(item, path=path, repository_root=repository_root))

        result = (tuple(parsed), skipped, tuple(notes))
        self._scan_cache[cache_key] = result
        return result

    def _build_summary(
        self,
        sessions: list[NativeSessionAnalytics],
        *,
        repository_root: Path | None,
        skipped: int,
        notes: tuple[str, ...],
    ) -> NativeRepositoryAnalyticsSummary:
        tool_counts: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "first_seen_at": None, "last_seen_at": None})
        first_tool_distribution: Counter[str] = Counter()
        first_high_value_tool_distribution: Counter[str] = Counter()
        correlation_quality_mix: Counter[str] = Counter()
        totals = NativeTranscriptMetrics()
        total_tokens = 0
        token_breakdowns: Counter[str] = Counter()
        first_suitcode_tool_indices: list[int] = []
        first_high_value_tool_indices: list[int] = []
        tokens_before_first_suitcode: list[int] = []
        tokens_before_first_high_value: list[int] = []
        latest = max(sessions, key=lambda item: item.artifact.last_event_at, default=None)
        native_input_tokens = 0
        native_output_tokens = 0
        native_cache_creation_tokens = 0
        native_cache_read_tokens = 0
        any_native_reported_tokens = False

        for session in sessions:
            correlation_quality_mix[session.correlation_quality.value] += 1
            if session.first_suitcode_tool is not None:
                first_tool_distribution[session.first_suitcode_tool] += 1
            if session.first_suitcode_tool_index is not None:
                first_suitcode_tool_indices.append(session.first_suitcode_tool_index)
            if session.first_high_value_suitcode_tool is not None:
                first_high_value_tool_distribution[session.first_high_value_suitcode_tool] += 1
            if session.first_high_value_suitcode_tool_index is not None:
                first_high_value_tool_indices.append(session.first_high_value_suitcode_tool_index)
            totals = NativeTranscriptMetrics(
                event_count=totals.event_count + session.transcript_metrics.event_count,
                message_event_count=totals.message_event_count + session.transcript_metrics.message_event_count,
                tool_event_count=totals.tool_event_count + session.transcript_metrics.tool_event_count,
                assistant_message_count=totals.assistant_message_count + session.transcript_metrics.assistant_message_count,
                user_message_count=totals.user_message_count + session.transcript_metrics.user_message_count,
                mcp_tool_call_count=totals.mcp_tool_call_count + session.transcript_metrics.mcp_tool_call_count,
                suitcode_tool_call_count=totals.suitcode_tool_call_count + session.transcript_metrics.suitcode_tool_call_count,
                approx_input_characters=totals.approx_input_characters + session.transcript_metrics.approx_input_characters,
                approx_output_characters=totals.approx_output_characters + session.transcript_metrics.approx_output_characters,
                native_reported_input_tokens=(
                    (totals.native_reported_input_tokens or 0) + (session.transcript_metrics.native_reported_input_tokens or 0)
                    if totals.native_reported_input_tokens is not None or session.transcript_metrics.native_reported_input_tokens is not None
                    else None
                ),
                native_reported_output_tokens=(
                    (totals.native_reported_output_tokens or 0) + (session.transcript_metrics.native_reported_output_tokens or 0)
                    if totals.native_reported_output_tokens is not None or session.transcript_metrics.native_reported_output_tokens is not None
                    else None
                ),
                native_reported_cache_creation_tokens=(
                    (totals.native_reported_cache_creation_tokens or 0)
                    + (session.transcript_metrics.native_reported_cache_creation_tokens or 0)
                    if totals.native_reported_cache_creation_tokens is not None
                    or session.transcript_metrics.native_reported_cache_creation_tokens is not None
                    else None
                ),
                native_reported_cache_read_tokens=(
                    (totals.native_reported_cache_read_tokens or 0) + (session.transcript_metrics.native_reported_cache_read_tokens or 0)
                    if totals.native_reported_cache_read_tokens is not None
                    or session.transcript_metrics.native_reported_cache_read_tokens is not None
                    else None
                ),
            )
            if session.transcript_metrics.native_reported_input_tokens is not None:
                native_input_tokens += session.transcript_metrics.native_reported_input_tokens
                any_native_reported_tokens = True
            if session.transcript_metrics.native_reported_output_tokens is not None:
                native_output_tokens += session.transcript_metrics.native_reported_output_tokens
                any_native_reported_tokens = True
            if session.transcript_metrics.native_reported_cache_creation_tokens is not None:
                native_cache_creation_tokens += session.transcript_metrics.native_reported_cache_creation_tokens
                any_native_reported_tokens = True
            if session.transcript_metrics.native_reported_cache_read_tokens is not None:
                native_cache_read_tokens += session.transcript_metrics.native_reported_cache_read_tokens
                any_native_reported_tokens = True
            if session.token_breakdown is not None:
                breakdown = session.token_breakdown
                total_tokens += breakdown.total_tokens
                token_breakdowns["user_message_tokens"] += breakdown.user_message_tokens
                token_breakdowns["assistant_message_tokens"] += breakdown.assistant_message_tokens
                token_breakdowns["mcp_tool_call_tokens"] += breakdown.mcp_tool_call_tokens
                token_breakdowns["mcp_tool_output_tokens"] += breakdown.mcp_tool_output_tokens
                token_breakdowns["custom_tool_call_tokens"] += breakdown.custom_tool_call_tokens
                token_breakdowns["custom_tool_output_tokens"] += breakdown.custom_tool_output_tokens
                token_breakdowns["terminal_output_tokens"] += breakdown.terminal_output_tokens
                token_breakdowns["reasoning_summary_tokens"] += breakdown.reasoning_summary_tokens
                if breakdown.tokens_before_first_suitcode_tool is not None:
                    tokens_before_first_suitcode.append(breakdown.tokens_before_first_suitcode_tool)
                if breakdown.tokens_before_first_high_value_suitcode_tool is not None:
                    tokens_before_first_high_value.append(breakdown.tokens_before_first_high_value_suitcode_tool)
            for tool in session.suitcode_tools:
                stats = tool_counts[tool.tool_name]
                stats["count"] = int(stats["count"]) + tool.call_count
                first_seen = stats["first_seen_at"]
                if first_seen is None or (tool.first_seen_at is not None and tool.first_seen_at < first_seen):
                    stats["first_seen_at"] = tool.first_seen_at
                last_seen = stats["last_seen_at"]
                if last_seen is None or (tool.last_seen_at is not None and tool.last_seen_at > last_seen):
                    stats["last_seen_at"] = tool.last_seen_at

        tool_usage = tuple(
            NativeSuitCodeToolUse(
                tool_name=tool_name,
                call_count=int(stats["count"]),
                first_seen_at=stats["first_seen_at"],
                last_seen_at=stats["last_seen_at"],
            )
            for tool_name, stats in sorted(tool_counts.items(), key=lambda item: (-int(item[1]["count"]), item[0]))
        )
        sessions_using_suitcode = sum(1 for item in sessions if item.used_suitcode or item.correlated_event_count > 0)
        return NativeRepositoryAnalyticsSummary(
            repository_root=(str(repository_root) if repository_root is not None else None),
            session_count=len(sessions),
            sessions_using_suitcode=sessions_using_suitcode,
            sessions_without_suitcode=len(sessions) - sessions_using_suitcode,
            sessions_without_high_value_suitcode=sum(1 for item in sessions if item.used_no_high_value_suitcode_tool),
            sessions_with_late_suitcode_adoption=sum(1 for item in sessions if item.late_suitcode_adoption),
            sessions_with_late_high_value_adoption=sum(1 for item in sessions if item.late_high_value_suitcode_adoption),
            sessions_with_shell_heavy_pre_suitcode=sum(1 for item in sessions if item.shell_heavy_before_suitcode),
            skipped_artifacts=skipped,
            tool_usage=tool_usage,
            first_tool_distribution=dict(first_tool_distribution),
            first_high_value_tool_distribution=dict(first_high_value_tool_distribution),
            correlation_quality_mix=dict(correlation_quality_mix),
            transcript_metrics=totals,
            avg_first_suitcode_tool_index=(sum(first_suitcode_tool_indices) / len(first_suitcode_tool_indices) if first_suitcode_tool_indices else None),
            avg_first_high_value_suitcode_tool_index=(sum(first_high_value_tool_indices) / len(first_high_value_tool_indices) if first_high_value_tool_indices else None),
            total_tokens=(total_tokens if any(item.token_breakdown is not None for item in sessions) else None),
            avg_tokens_per_session=(total_tokens / len(sessions) if sessions and any(item.token_breakdown is not None for item in sessions) else None),
            avg_tokens_before_first_suitcode_tool=(sum(tokens_before_first_suitcode) / len(tokens_before_first_suitcode) if tokens_before_first_suitcode else None),
            avg_tokens_before_first_high_value_suitcode_tool=(sum(tokens_before_first_high_value) / len(tokens_before_first_high_value) if tokens_before_first_high_value else None),
            token_breakdowns_by_kind=dict(token_breakdowns),
            native_reported_input_tokens=(native_input_tokens if any_native_reported_tokens else None),
            native_reported_output_tokens=(native_output_tokens if any_native_reported_tokens else None),
            native_reported_cache_creation_tokens=(native_cache_creation_tokens if any_native_reported_tokens else None),
            native_reported_cache_read_tokens=(native_cache_read_tokens if any_native_reported_tokens else None),
            latest_session_id=(latest.session_id if latest is not None else None),
            latest_session_at=(latest.artifact.last_event_at if latest is not None else None),
            notes=notes,
        )
