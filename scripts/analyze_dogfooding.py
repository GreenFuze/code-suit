from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.analytics.claude_analytics_service import ClaudeAnalyticsService
from suitcode.analytics.claude_session_store import ClaudeSessionStore
from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder
from suitcode.analytics.codex_analytics_service import CodexAnalyticsService
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.cursor_analytics_service import CursorAnalyticsService
from suitcode.analytics.cursor_session_store import CursorSessionStore
from suitcode.analytics.cursor_transcript_capture import CursorTranscriptCaptureBuilder
from suitcode.analytics.inefficiency import InefficiencyDetector
from suitcode.analytics.models import AnalyticsEvent
from suitcode.analytics.native_agent_models import NativeRepositoryAnalyticsSummary, NativeSessionAnalytics, NativeSuitCodeToolUse, NativeTranscriptMetrics
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.token_estimation import TokenEstimator
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.evaluation.metadata_models import AgentKind
from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS
from suitcode.core.repository import Repository


TRACKED_REPOSITORIES_PATH = PROJECT_ROOT / "docs" / "dogfooding" / "tracked_repositories.v1.json"
EXCLUDED_ANALYTICS_TOOLS = (
    "get_analytics_summary",
    "get_tool_usage_analytics",
    "get_inefficient_tool_calls",
    "get_mcp_benchmark_report",
)


@dataclass(frozen=True)
class TrackedRepository:
    label: str
    repository_root: Path
    ecosystems: tuple[str, ...]
    notes: tuple[str, ...]
    is_primary: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_dogfooding")
    parser.add_argument("--repository-root", type=str, default=None)
    parser.add_argument("--tracked-label", type=str, default=None)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--include-global-mcp", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--session-limit", type=int, default=100)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def load_tracked_repositories(path: Path = TRACKED_REPOSITORIES_PATH) -> tuple[TrackedRepository, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[TrackedRepository] = []
    for raw in payload["repositories"]:
        items.append(
            TrackedRepository(
                label=str(raw["label"]).strip(),
                repository_root=Path(raw["repository_root"]).expanduser().resolve(),
                ecosystems=tuple(str(item).strip() for item in raw.get("ecosystems", [])),
                notes=tuple(str(item).strip() for item in raw.get("notes", [])),
                is_primary=bool(raw.get("is_primary", False)),
            )
        )
    return tuple(items)


def resolve_tracked_repository(*, repository_root: str | None, tracked_label: str | None) -> TrackedRepository:
    tracked = load_tracked_repositories()
    if tracked_label:
        normalized = tracked_label.strip()
        for item in tracked:
            if item.label == normalized:
                return item
        raise ValueError(f"unknown tracked repository label: `{tracked_label}`")
    if repository_root:
        root = Path(repository_root).expanduser().resolve()
        return TrackedRepository(
            label=_slugify(root.name or "repository"),
            repository_root=root,
            ecosystems=tuple(),
            notes=tuple(),
            is_primary=False,
        )
    raise ValueError("either --tracked-label or --repository-root is required")


def build_native_services(include_tokens: bool = True) -> dict[str, object]:
    analytics_store = JsonlAnalyticsStore(AnalyticsSettings.from_env())
    correlation = AnalyticsCorrelationService(analytics_store)
    estimator = TranscriptTokenEstimator() if include_tokens else None
    return {
        AgentKind.CODEX.value: CodexAnalyticsService(
            CodexSessionStore(),
            correlation_service=correlation,
            capture_builder=CodexTranscriptCaptureBuilder(),
            token_estimator=estimator,
        ),
        AgentKind.CLAUDE.value: ClaudeAnalyticsService(
            ClaudeSessionStore(),
            correlation_service=correlation,
            capture_builder=ClaudeTranscriptCaptureBuilder(),
            token_estimator=estimator,
        ),
        AgentKind.CURSOR.value: CursorAnalyticsService(
            CursorSessionStore(),
            correlation_service=correlation,
            capture_builder=CursorTranscriptCaptureBuilder(CursorSessionStore()),
            token_estimator=estimator,
        ),
    }


def summarize_native_sessions(
    *,
    sessions: tuple[NativeSessionAnalytics, ...],
    repository_root: Path,
    agent_name: str,
) -> dict[str, object]:
    tool_counts: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "first_seen_at": None, "last_seen_at": None})
    first_tool_distribution: Counter[str] = Counter()
    first_high_value_distribution: Counter[str] = Counter()
    correlation_quality_mix: Counter[str] = Counter()
    token_breakdowns: Counter[str] = Counter()
    totals = NativeTranscriptMetrics()
    first_tool_indexes: list[int] = []
    first_high_value_indexes: list[int] = []
    tokens_before_first_tool: list[int] = []
    tokens_before_first_high_value: list[int] = []
    total_tokens = 0
    notes: list[str] = []
    for session in sessions:
        correlation_quality_mix[session.correlation_quality.value] += 1
        if session.first_suitcode_tool:
            first_tool_distribution[session.first_suitcode_tool] += 1
        if session.first_suitcode_tool_index is not None:
            first_tool_indexes.append(session.first_suitcode_tool_index)
        if session.first_high_value_suitcode_tool:
            first_high_value_distribution[session.first_high_value_suitcode_tool] += 1
        if session.first_high_value_suitcode_tool_index is not None:
            first_high_value_indexes.append(session.first_high_value_suitcode_tool_index)
        metrics = session.transcript_metrics
        totals = NativeTranscriptMetrics(
            event_count=totals.event_count + metrics.event_count,
            message_event_count=totals.message_event_count + metrics.message_event_count,
            tool_event_count=totals.tool_event_count + metrics.tool_event_count,
            assistant_message_count=totals.assistant_message_count + metrics.assistant_message_count,
            user_message_count=totals.user_message_count + metrics.user_message_count,
            mcp_tool_call_count=totals.mcp_tool_call_count + metrics.mcp_tool_call_count,
            suitcode_tool_call_count=totals.suitcode_tool_call_count + metrics.suitcode_tool_call_count,
            approx_input_characters=totals.approx_input_characters + metrics.approx_input_characters,
            approx_output_characters=totals.approx_output_characters + metrics.approx_output_characters,
            native_reported_input_tokens=(totals.native_reported_input_tokens or 0) + (metrics.native_reported_input_tokens or 0)
            if totals.native_reported_input_tokens is not None or metrics.native_reported_input_tokens is not None
            else None,
            native_reported_output_tokens=(totals.native_reported_output_tokens or 0) + (metrics.native_reported_output_tokens or 0)
            if totals.native_reported_output_tokens is not None or metrics.native_reported_output_tokens is not None
            else None,
            native_reported_cache_creation_tokens=(totals.native_reported_cache_creation_tokens or 0) + (metrics.native_reported_cache_creation_tokens or 0)
            if totals.native_reported_cache_creation_tokens is not None or metrics.native_reported_cache_creation_tokens is not None
            else None,
            native_reported_cache_read_tokens=(totals.native_reported_cache_read_tokens or 0) + (metrics.native_reported_cache_read_tokens or 0)
            if totals.native_reported_cache_read_tokens is not None or metrics.native_reported_cache_read_tokens is not None
            else None,
        )
        if session.token_breakdown is not None:
            total_tokens += session.token_breakdown.total_tokens
            token_breakdowns["user_message_tokens"] += session.token_breakdown.user_message_tokens
            token_breakdowns["assistant_message_tokens"] += session.token_breakdown.assistant_message_tokens
            token_breakdowns["mcp_tool_call_tokens"] += session.token_breakdown.mcp_tool_call_tokens
            token_breakdowns["mcp_tool_output_tokens"] += session.token_breakdown.mcp_tool_output_tokens
            token_breakdowns["custom_tool_call_tokens"] += session.token_breakdown.custom_tool_call_tokens
            token_breakdowns["custom_tool_output_tokens"] += session.token_breakdown.custom_tool_output_tokens
            token_breakdowns["terminal_output_tokens"] += session.token_breakdown.terminal_output_tokens
            token_breakdowns["reasoning_summary_tokens"] += session.token_breakdown.reasoning_summary_tokens
            if session.token_breakdown.tokens_before_first_suitcode_tool is not None:
                tokens_before_first_tool.append(session.token_breakdown.tokens_before_first_suitcode_tool)
            if session.token_breakdown.tokens_before_first_high_value_suitcode_tool is not None:
                tokens_before_first_high_value.append(session.token_breakdown.tokens_before_first_high_value_suitcode_tool)
        for tool in session.suitcode_tools:
            stats = tool_counts[tool.tool_name]
            stats["count"] = int(stats["count"]) + tool.call_count
            first_seen = stats["first_seen_at"]
            if first_seen is None or (tool.first_seen_at is not None and tool.first_seen_at < first_seen):
                stats["first_seen_at"] = tool.first_seen_at
            last_seen = stats["last_seen_at"]
            if last_seen is None or (tool.last_seen_at is not None and tool.last_seen_at > last_seen):
                stats["last_seen_at"] = tool.last_seen_at
        notes.extend(session.notes)

    if agent_name == AgentKind.CURSOR.value and not first_tool_indexes:
        notes.append("Cursor tool-order metrics are partial because current native artifacts expose weaker tool traces.")

    top_tools = tuple(
        {
            "tool_name": tool_name,
            "call_count": int(stats["count"]),
            "first_seen_at": stats["first_seen_at"].isoformat() if stats["first_seen_at"] is not None else None,
            "last_seen_at": stats["last_seen_at"].isoformat() if stats["last_seen_at"] is not None else None,
        }
        for tool_name, stats in sorted(tool_counts.items(), key=lambda item: (-int(item[1]["count"]), item[0]))[:10]
    )
    sessions_using_suitcode = sum(1 for item in sessions if item.used_suitcode or item.correlated_event_count > 0)
    return {
        "agent_kind": agent_name,
        "repository_root": str(repository_root),
        "session_count": len(sessions),
        "sessions_using_suitcode": sessions_using_suitcode,
        "sessions_without_suitcode": len(sessions) - sessions_using_suitcode,
        "first_tool_distribution": dict(first_tool_distribution),
        "first_high_value_tool_distribution": dict(first_high_value_distribution),
        "avg_first_suitcode_tool_index": (sum(first_tool_indexes) / len(first_tool_indexes) if first_tool_indexes else None),
        "avg_first_high_value_suitcode_tool_index": (
            sum(first_high_value_indexes) / len(first_high_value_indexes) if first_high_value_indexes else None
        ),
        "total_tokens": (total_tokens if any(item.token_breakdown is not None for item in sessions) else None),
        "avg_tokens_before_first_suitcode_tool": (
            sum(tokens_before_first_tool) / len(tokens_before_first_tool) if tokens_before_first_tool else None
        ),
        "avg_tokens_before_first_high_value_suitcode_tool": (
            sum(tokens_before_first_high_value) / len(tokens_before_first_high_value) if tokens_before_first_high_value else None
        ),
        "correlation_quality_mix": dict(correlation_quality_mix),
        "transcript_metrics": totals.model_dump(mode="json"),
        "token_breakdowns_by_kind": dict(token_breakdowns),
        "top_tools": top_tools,
        "notes": tuple(dict.fromkeys(note for note in notes if note.strip())),
    }


def summarize_mcp_events(
    *,
    repository_root: Path,
    since: datetime,
    include_global: bool,
) -> dict[str, object]:
    settings = AnalyticsSettings.from_env()
    store = JsonlAnalyticsStore(settings)
    events = store.load_events(repository_root=repository_root, include_global=include_global)
    filtered = tuple(item for item in events if _parse_utc(item.timestamp_utc) >= since)
    estimator = TokenEstimator()
    detector = InefficiencyDetector(
        tool_catalog=tuple(sorted(TOOL_DESCRIPTIONS)),
        excluded_tools=EXCLUDED_ANALYTICS_TOOLS,
    )
    filtered = tuple(item for item in filtered if item.tool_name not in EXCLUDED_ANALYTICS_TOOLS)
    tool_counts = Counter(item.tool_name for item in filtered)
    estimates = [estimator.estimate(item) for item in filtered]
    inefficiencies = detector.detect(filtered)
    return {
        "total_calls": len(filtered),
        "estimated_tokens": sum(item.actual_tokens_estimate for item in estimates),
        "estimated_tokens_saved": sum(item.estimated_tokens_saved for item in estimates),
        "top_tools": tuple(tool for tool, _ in tool_counts.most_common(10)),
        "inefficiency_mix": dict(Counter(item.kind for item in inefficiencies)),
        "inefficiency_count": len(inefficiencies),
    }


def build_dogfooding_summary(
    *,
    tracked: TrackedRepository,
    days: int,
    include_global_mcp: bool,
    session_limit: int,
) -> dict[str, object]:
    if days <= 0:
        raise ValueError("--days must be > 0")
    if session_limit <= 0:
        raise ValueError("--session-limit must be > 0")
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    support = Repository.support_for_path(tracked.repository_root)
    services = build_native_services(include_tokens=True)
    agent_summaries: list[dict[str, object]] = []
    for agent_kind in (AgentKind.CODEX.value, AgentKind.CLAUDE.value, AgentKind.CURSOR.value):
        service = services[agent_kind]
        sessions = tuple(
            item
            for item in service.session_analytics(repository_root=tracked.repository_root)[:session_limit]
            if item.artifact.last_event_at >= since
        )
        agent_summaries.append(
            summarize_native_sessions(
                sessions=sessions,
                repository_root=tracked.repository_root,
                agent_name=agent_kind,
            )
        )
    mcp_summary = summarize_mcp_events(
        repository_root=tracked.repository_root,
        since=since,
        include_global=include_global_mcp,
    )
    return {
        "schema_version": "1.0",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "window_days": days,
        "window_start_utc": since.isoformat().replace("+00:00", "Z"),
        "window_end_utc": now.isoformat().replace("+00:00", "Z"),
        "tracked_repository": {
            "label": tracked.label,
            "repository_root": str(tracked.repository_root),
            "ecosystems": tracked.ecosystems,
            "notes": tracked.notes,
            "is_primary": tracked.is_primary,
        },
        "support": {
            "is_supported": support.is_supported,
            "provider_ids": support.provider_ids,
            "repository_root": str(support.repository_root),
        },
        "mcp_analytics": mcp_summary,
        "agents": tuple(agent_summaries),
    }


def write_summary_bundle(summary: dict[str, object], *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "summary.json"
    md_path = output_dir / "summary.md"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_summary_markdown(summary), encoding="utf-8")
    return json_path, md_path


def render_summary_markdown(summary: dict[str, object]) -> str:
    tracked = summary["tracked_repository"]
    support = summary["support"]
    mcp = summary["mcp_analytics"]
    lines = [
        "# SuitCode Dogfooding Summary",
        "",
        f"- label: `{tracked['label']}`",
        f"- repository root: `{tracked['repository_root']}`",
        f"- support status: `{'supported' if support['is_supported'] else 'unsupported'}`",
        f"- providers: `{', '.join(support['provider_ids']) if support['provider_ids'] else '(none)'}`",
        f"- window: `{summary['window_start_utc']}` -> `{summary['window_end_utc']}`",
        "",
        "## MCP Analytics",
        "",
        f"- total calls: `{mcp['total_calls']}`",
        f"- estimated tokens: `{mcp['estimated_tokens']}`",
        f"- estimated tokens saved: `{mcp['estimated_tokens_saved']}`",
        f"- top tools: `{', '.join(mcp['top_tools']) if mcp['top_tools'] else '(none)'}`",
        f"- inefficiency mix: `{mcp['inefficiency_mix']}`",
        "",
        "## Native Agent Summaries",
        "",
    ]
    for agent in summary["agents"]:
        lines.extend(
            [
                f"### {agent['agent_kind'].capitalize()}",
                "",
                f"- session count: `{agent['session_count']}`",
                f"- sessions using SuitCode: `{agent['sessions_using_suitcode']}`",
                f"- avg first SuitCode tool index: `{agent['avg_first_suitcode_tool_index']}`",
                f"- avg first high-value SuitCode tool index: `{agent['avg_first_high_value_suitcode_tool_index']}`",
                f"- total transcript-estimated tokens: `{agent['total_tokens']}`",
                f"- avg tokens before first SuitCode tool: `{agent['avg_tokens_before_first_suitcode_tool']}`",
                f"- avg tokens before first high-value SuitCode tool: `{agent['avg_tokens_before_first_high_value_suitcode_tool']}`",
                f"- correlation quality mix: `{agent['correlation_quality_mix']}`",
                f"- top tools: `{', '.join(item['tool_name'] for item in agent['top_tools']) if agent['top_tools'] else '(none)'}`",
            ]
        )
        if agent["notes"]:
            lines.append("- notes:")
            for note in agent["notes"]:
                lines.append(f"  - {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "repository"


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def default_output_dir(*, tracked: TrackedRepository, generated_at_utc: str) -> Path:
    stamp = generated_at_utc.replace(":", "-").replace("+00:00", "Z")
    return tracked.repository_root / ".suit" / "dogfooding" / f"{stamp}__{tracked.label}"


def main() -> None:
    args = build_parser().parse_args()
    tracked = resolve_tracked_repository(repository_root=args.repository_root, tracked_label=args.tracked_label)
    summary = build_dogfooding_summary(
        tracked=tracked,
        days=args.days,
        include_global_mcp=args.include_global_mcp,
        session_limit=args.session_limit,
    )
    if args.as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    generated = summary["generated_at_utc"]
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_output_dir(
        tracked=tracked,
        generated_at_utc=generated,
    )
    json_path, md_path = write_summary_bundle(summary, output_dir=output_dir)
    print(f"Dogfooding summary written:")
    print(f"- {json_path}")
    print(f"- {md_path}")


if __name__ == "__main__":
    main()
