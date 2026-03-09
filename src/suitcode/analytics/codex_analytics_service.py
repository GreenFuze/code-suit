from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.codex_session_parser import CodexSessionParser
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_usage_policy import with_usage_flags
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.native_agent_models import (
    CodexRepositoryAnalyticsSummary,
    CodexSessionAnalytics,
    CodexSuitCodeToolUse,
    CodexTranscriptMetrics,
)
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


class CodexAnalyticsService:
    def __init__(
        self,
        store: CodexSessionStore,
        *,
        parser: CodexSessionParser | None = None,
        correlation_service: AnalyticsCorrelationService | None = None,
        capture_builder: CodexTranscriptCaptureBuilder | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
    ) -> None:
        self._store = store
        self._parser = parser or CodexSessionParser()
        self._correlation_service = correlation_service
        self._capture_builder = capture_builder
        self._token_estimator = token_estimator

    def session_analytics(
        self,
        repository_root: Path | None = None,
        session_id: str | None = None,
    ) -> tuple[CodexSessionAnalytics, ...]:
        sessions = self._store.list_sessions(repository_root=repository_root, session_id=session_id)
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        items: list[CodexSessionAnalytics] = []
        for path in sessions:
            items.append(self._enrich(self._parser.parse(path), path=path, repository_root=normalized_root))
        return tuple(items)

    def repository_summary(self, repository_root: Path | None = None) -> CodexRepositoryAnalyticsSummary:
        normalized_root = repository_root.expanduser().resolve() if repository_root is not None else None
        parsed: list[CodexSessionAnalytics] = []
        skipped = 0
        notes: list[str] = []
        for path in self._store.candidate_sessions():
            try:
                meta = self._store.session_meta(path)
            except ValueError as exc:
                skipped += 1
                notes.append(str(exc))
                continue
            if normalized_root is not None:
                cwd = meta["cwd"]
                if cwd is None or cwd != normalized_root:
                    continue
            try:
                item = self._parser.parse(path)
            except ValueError as exc:
                skipped += 1
                notes.append(str(exc))
                continue
            parsed.append(self._enrich(item, path=path, repository_root=normalized_root))
        return self._build_summary(parsed, repository_root=normalized_root, skipped=skipped, notes=tuple(notes))

    def latest_repository_session(self, repository_root: Path) -> CodexSessionAnalytics | None:
        normalized_root = repository_root.expanduser().resolve()
        latest = self._store.latest_session(repository_root=normalized_root)
        if latest is None:
            return None
        return self._enrich(self._parser.parse(latest), path=latest, repository_root=normalized_root)

    def _correlate(self, session: CodexSessionAnalytics, repository_root: Path | None) -> CodexSessionAnalytics:
        if self._correlation_service is None:
            return session
        return self._correlation_service.correlate_codex_session(session, repository_root)

    def _enrich(self, session: CodexSessionAnalytics, *, path: Path, repository_root: Path | None) -> CodexSessionAnalytics:
        correlated = self._correlate(session, repository_root)
        enriched = correlated
        if self._capture_builder is not None:
            enriched = enriched.model_copy(update={"transcript_capture": self._capture_builder.build(path)})
        if self._token_estimator is not None and enriched.transcript_capture is not None:
            enriched = self._token_estimator.estimate_codex_session(enriched)
        return with_usage_flags(enriched)

    def _build_summary(
        self,
        sessions: list[CodexSessionAnalytics],
        *,
        repository_root: Path | None,
        skipped: int,
        notes: tuple[str, ...],
    ) -> CodexRepositoryAnalyticsSummary:
        tool_counts: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "first_seen_at": None, "last_seen_at": None})
        first_tool_distribution: Counter[str] = Counter()
        first_high_value_tool_distribution: Counter[str] = Counter()
        correlation_quality_mix: Counter[str] = Counter()
        totals = CodexTranscriptMetrics()
        total_tokens = 0
        token_breakdowns: Counter[str] = Counter()
        first_suitcode_tool_indices: list[int] = []
        first_high_value_tool_indices: list[int] = []
        tokens_before_first_suitcode: list[int] = []
        tokens_before_first_high_value: list[int] = []
        latest = max(sessions, key=lambda item: item.artifact.last_event_at, default=None)

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
            totals = CodexTranscriptMetrics(
                event_count=totals.event_count + session.transcript_metrics.event_count,
                message_event_count=totals.message_event_count + session.transcript_metrics.message_event_count,
                tool_event_count=totals.tool_event_count + session.transcript_metrics.tool_event_count,
                assistant_message_count=totals.assistant_message_count + session.transcript_metrics.assistant_message_count,
                user_message_count=totals.user_message_count + session.transcript_metrics.user_message_count,
                mcp_tool_call_count=totals.mcp_tool_call_count + session.transcript_metrics.mcp_tool_call_count,
                suitcode_tool_call_count=totals.suitcode_tool_call_count + session.transcript_metrics.suitcode_tool_call_count,
                approx_input_characters=totals.approx_input_characters + session.transcript_metrics.approx_input_characters,
                approx_output_characters=totals.approx_output_characters + session.transcript_metrics.approx_output_characters,
            )
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
            CodexSuitCodeToolUse(
                tool_name=tool_name,
                call_count=int(stats["count"]),
                first_seen_at=stats["first_seen_at"],
                last_seen_at=stats["last_seen_at"],
            )
            for tool_name, stats in sorted(
                tool_counts.items(),
                key=lambda item: (-int(item[1]["count"]), item[0]),
            )
        )
        sessions_using_suitcode = sum(1 for item in sessions if item.used_suitcode)
        return CodexRepositoryAnalyticsSummary(
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
            avg_first_suitcode_tool_index=(
                sum(first_suitcode_tool_indices) / len(first_suitcode_tool_indices)
                if first_suitcode_tool_indices
                else None
            ),
            avg_first_high_value_suitcode_tool_index=(
                sum(first_high_value_tool_indices) / len(first_high_value_tool_indices)
                if first_high_value_tool_indices
                else None
            ),
            total_tokens=(total_tokens if any(item.token_breakdown is not None for item in sessions) else None),
            avg_tokens_per_session=(
                total_tokens / len(sessions)
                if sessions and any(item.token_breakdown is not None for item in sessions)
                else None
            ),
            avg_tokens_before_first_suitcode_tool=(
                sum(tokens_before_first_suitcode) / len(tokens_before_first_suitcode)
                if tokens_before_first_suitcode
                else None
            ),
            avg_tokens_before_first_high_value_suitcode_tool=(
                sum(tokens_before_first_high_value) / len(tokens_before_first_high_value)
                if tokens_before_first_high_value
                else None
            ),
            token_breakdowns_by_kind=dict(token_breakdowns),
            latest_session_id=(latest.session_id if latest is not None else None),
            latest_session_at=(latest.artifact.last_event_at if latest is not None else None),
            notes=notes,
        )
