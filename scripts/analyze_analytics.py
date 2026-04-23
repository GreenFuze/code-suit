from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.analytics.live_usage_filters import event_matches_live_filters, parse_cutoff
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_analytics")
    parser.add_argument("--repository-root", type=str, default=None)
    parser.add_argument("--session-id", type=str, default=None)
    parser.add_argument("--tool-name", type=str, default=None)
    parser.add_argument(
        "--include-global",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include global analytics stream (auto: false when --repository-root is set, true otherwise).",
    )
    parser.add_argument("--include-events", action="store_true")
    parser.add_argument("--event-limit", type=int, default=50)
    parser.add_argument("--since-utc", type=str, default=None)
    parser.add_argument("--since-hours", type=int, default=None)
    parser.add_argument("--exclude-test-artifacts", action="store_true")
    parser.add_argument("--exclude-benchmark-events", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _filtered_events(
    *,
    store: JsonlAnalyticsStore,
    repository_root: Path | None,
    include_global: bool,
    session_id: str | None,
    tool_name: str | None,
    event_limit: int,
    event_filter,
):
    if event_limit <= 0:
        raise ValueError("--event-limit must be > 0")
    events = store.load_events(repository_root=repository_root, include_global=include_global)
    filtered = []
    for event in events:
        if event_filter is not None and not event_filter(event):
            continue
        if session_id is not None and event.session_id != session_id:
            continue
        if tool_name is not None and event.tool_name != tool_name:
            continue
        filtered.append(event)
    filtered.sort(key=lambda item: (item.timestamp_utc, item.event_id), reverse=True)
    return tuple(filtered[:event_limit])


def main() -> None:
    args = build_parser().parse_args()
    settings = AnalyticsSettings.from_env()
    store = JsonlAnalyticsStore(settings)
    aggregator = AnalyticsAggregator(
        store,
        tool_catalog=tuple(sorted(TOOL_DESCRIPTIONS)),
        excluded_tools=(
            "get_analytics_summary",
            "get_tool_usage_analytics",
            "get_inefficient_tool_calls",
            "get_mcp_benchmark_report",
        ),
    )
    repository_root = Path(args.repository_root).expanduser().resolve() if args.repository_root else None
    include_global = args.include_global if args.include_global is not None else repository_root is None
    cutoff = parse_cutoff(since_utc=args.since_utc, since_hours=args.since_hours)
    event_filter = lambda item: event_matches_live_filters(
        item,
        cutoff=cutoff,
        exclude_test_artifacts=args.exclude_test_artifacts,
        exclude_benchmark_events=args.exclude_benchmark_events,
    )

    summary = aggregator.summary(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
        event_filter=event_filter,
    )
    tool_usage = aggregator.tool_usage(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
        event_filter=event_filter,
    )
    inefficiencies = aggregator.inefficient_calls(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
        event_filter=event_filter,
    )
    events = (
        _filtered_events(
            store=store,
            repository_root=repository_root,
            include_global=include_global,
            session_id=args.session_id,
            tool_name=args.tool_name,
            event_limit=args.event_limit,
            event_filter=event_filter,
        )
        if args.include_events
        else tuple()
    )

    if args.as_json:
        payload = {
            "filters": {
                "repository_root": (str(repository_root) if repository_root else None),
                "include_global": include_global,
                "session_id": args.session_id,
                "tool_name": args.tool_name,
                "since_utc": args.since_utc,
                "since_hours": args.since_hours,
                "exclude_test_artifacts": args.exclude_test_artifacts,
                "exclude_benchmark_events": args.exclude_benchmark_events,
            },
            "summary": summary.model_dump(mode="json"),
            "tool_usage": [item.model_dump(mode="json") for item in tool_usage],
            "inefficiencies": [item.model_dump(mode="json") for item in inefficiencies],
        }
        if args.include_events:
            payload["events"] = [item.model_dump(mode="json") for item in events]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("SuitCode Analytics")
    print("==================")
    print(f"Repository root filter: {repository_root or '(none)'}")
    print(f"Include global stream: {include_global}")
    print(f"Session filter: {args.session_id or '(none)'}")
    print(f"Tool filter: {args.tool_name or '(none)'}")
    print(f"Since UTC: {args.since_utc or '(none)'}")
    print(f"Since hours: {args.since_hours if args.since_hours is not None else '(none)'}")
    print(f"Exclude test artifacts: {args.exclude_test_artifacts}")
    print(f"Exclude benchmark events: {args.exclude_benchmark_events}")
    print()
    print(f"Total calls: {summary.total_calls}")
    print(f"Started calls: {summary.started_calls}")
    print(f"Finished calls: {summary.finished_calls}")
    print(f"Unfinished calls: {summary.unfinished_calls}")
    print(f"Success calls: {summary.success_calls}")
    print(f"Error calls: {summary.error_calls}")
    print(f"P50 duration (ms): {summary.p50_duration_ms}")
    print(f"P95 duration (ms): {summary.p95_duration_ms}")
    print(f"Estimated tokens: {summary.estimated_tokens}")
    print(f"Estimated tokens saved: {summary.estimated_tokens_saved}")
    print(f"Confidence mix: {summary.confidence_mix}")
    print(f"Top tools: {', '.join(summary.top_tools) if summary.top_tools else '(none)'}")
    print()
    print("Per-tool usage")
    print("--------------")
    for item in tool_usage:
        print(
            f"{item.tool_name}: calls={item.total_calls}, unfinished={item.unfinished_calls}, errors={item.error_calls}, "
            f"p95={item.p95_duration_ms}ms, est_saved={item.estimated_tokens_saved}"
        )
    print()
    print("Inefficiencies")
    print("--------------")
    if not inefficiencies:
        print("(none)")
    for item in inefficiencies:
        tool = item.tool_name or "-"
        session = item.session_id or "-"
        print(f"[{item.kind}] session={session} tool={tool} count={item.count} -> {item.description}")
    if args.include_events:
        print()
        print("Recent Events")
        print("-------------")
        if not events:
            print("(none)")
        for event in events:
            print(
                f"{event.timestamp_utc} [{event.status.value}] tool={event.tool_name} "
                f"session={event.session_id} duration={event.duration_ms}ms"
            )
            if event.invocation_id:
                print(f"  invocation_id={event.invocation_id}")
            if event.repository_root:
                print(f"  repository_root={event.repository_root}")
            if event.workspace_id or event.repository_id:
                print(f"  workspace_id={event.workspace_id or '-'} repository_id={event.repository_id or '-'}")
            if event.arguments_redacted:
                print(f"  arguments={event.arguments_redacted}")
            if event.error_class or event.error_message:
                print(f"  error={event.error_class or '-'}: {event.error_message or '-'}")


if __name__ == "__main__":
    main()
