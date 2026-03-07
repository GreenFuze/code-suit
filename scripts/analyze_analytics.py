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
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_analytics")
    parser.add_argument("--repository-root", type=str, default=None)
    parser.add_argument("--session-id", type=str, default=None)
    parser.add_argument(
        "--include-global",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include global analytics stream (auto: false when --repository-root is set, true otherwise).",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


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

    summary = aggregator.summary(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
    )
    tool_usage = aggregator.tool_usage(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
    )
    inefficiencies = aggregator.inefficient_calls(
        repository_root=repository_root,
        include_global=include_global,
        session_id=args.session_id,
    )

    if args.as_json:
        payload = {
            "filters": {
                "repository_root": (str(repository_root) if repository_root else None),
                "include_global": include_global,
                "session_id": args.session_id,
            },
            "summary": summary.model_dump(mode="json"),
            "tool_usage": [item.model_dump(mode="json") for item in tool_usage],
            "inefficiencies": [item.model_dump(mode="json") for item in inefficiencies],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("SuitCode Analytics")
    print("==================")
    print(f"Repository root filter: {repository_root or '(none)'}")
    print(f"Include global stream: {include_global}")
    print(f"Session filter: {args.session_id or '(none)'}")
    print()
    print(f"Total calls: {summary.total_calls}")
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
            f"{item.tool_name}: calls={item.total_calls}, errors={item.error_calls}, "
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


if __name__ == "__main__":
    main()
