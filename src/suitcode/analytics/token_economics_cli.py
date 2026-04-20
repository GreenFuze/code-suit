from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from suitcode.analytics.token_economics import TokenEconomicsReport, generate_token_economics_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suitcode-token-economics",
        description="Generate a deterministic SuitCode token-economics report from a workspace .suit directory.",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace root or its .suit directory. Defaults to the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full report as JSON instead of a compact text report.",
    )
    parser.add_argument(
        "--include-failures",
        action="store_true",
        help="Include failed SuitCode calls in aggregate call counts. Success-only is the default.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only include events at or after this UTC date/time. Accepts YYYY-MM-DD or ISO-8601.",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Only include events at or before this UTC date/time. Accepts YYYY-MM-DD or ISO-8601.",
    )
    parser.add_argument(
        "--exclude-session",
        action="append",
        default=[],
        help="Exclude a session id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--exclude-event",
        action="append",
        default=[],
        help="Exclude a tool_call_id. Can be provided multiple times.",
    )
    parser.add_argument(
        "--ignore-file",
        default=None,
        help=(
            "Optional JSON ignore file. Defaults to "
            ".suit/analytics/token-economics/ignore.json when present."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    workspace = Path(args.workspace)
    ignore = _load_ignore_file(workspace, args.ignore_file)
    report = generate_token_economics_report(
        workspace,
        include_failures=bool(args.include_failures),
        since=args.since,
        until=args.until,
        ignore_session_ids=set(args.exclude_session) | set(ignore.get("session_ids", [])),
        ignore_tool_call_ids=set(args.exclude_event) | set(ignore.get("tool_call_ids", [])),
    )
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    print(_format_text_report(report))


def _load_ignore_file(workspace: Path, ignore_file: str | None) -> dict[str, list[str]]:
    candidate = Path(ignore_file) if ignore_file is not None else _default_ignore_file(workspace)
    if candidate is None or not candidate.exists():
        return {"session_ids": [], "tool_call_ids": []}
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    return {
        "session_ids": _string_list(payload.get("session_ids")),
        "tool_call_ids": _string_list(payload.get("tool_call_ids")),
    }


def _default_ignore_file(workspace: Path) -> Path | None:
    resolved = workspace.expanduser().resolve()
    if resolved.name == ".suit":
        return resolved / "analytics" / "token-economics" / "ignore.json"
    return resolved / ".suit" / "analytics" / "token-economics" / "ignore.json"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _format_text_report(report: TokenEconomicsReport) -> str:
    lines = [
        "SuitCode Token Economics Report",
        f"Workspace: {report.workspace}",
        f"Generated at: {report.generated_at}",
        f"Failure policy: {'included' if report.include_failures else 'success-only'}",
        f"Ignored events: {report.ignored_event_count}",
        "",
        _aggregate_line("Total", report.total),
        "",
        "By day:",
        *_aggregate_table(report.by_day),
        "",
        "By tool:",
        *_aggregate_table(report.by_tool),
        "",
        "By session:",
        *_aggregate_table(report.by_session),
    ]
    return "\n".join(lines)


def _aggregate_line(label: str, item) -> str:
    return (
        f"{label}: calls={item.event_count} success={item.success_count} failures={item.failure_count} "
        f"avg_ms={item.avg_elapsed_ms:.2f} p50_ms={item.p50_elapsed_ms} "
        f"p95_ms={item.p95_elapsed_ms} max_ms={item.max_elapsed_ms} "
        f"response_tokens={item.total_response_tokens} evidence_tokens={item.total_evidence_footprint_tokens} "
        f"unique_evidence_tokens={item.unique_evidence_tokens} "
        f"evidence_reduction={item.evidence_token_reduction_pct:.2f}% "
        f"unique_evidence_reduction={item.session_unique_evidence_reduction_pct:.2f}%"
    )


def _aggregate_table(items) -> list[str]:
    if not items:
        return ["  (no events)"]
    rows = [
        "  name | calls | failures | avg_ms | p50_ms | p95_ms | max_ms | response_tokens | evidence_tokens | unique_evidence_tokens | evidence_reduction | unique_reduction"
    ]
    for item in items:
        rows.append(
            "  "
            f"{item.name} | {item.event_count} | {item.failure_count} | "
            f"{item.avg_elapsed_ms:.2f} | {item.p50_elapsed_ms} | {item.p95_elapsed_ms} | {item.max_elapsed_ms} | "
            f"{item.total_response_tokens} | "
            f"{item.total_evidence_footprint_tokens} | {item.unique_evidence_tokens} | "
            f"{item.evidence_token_reduction_pct:.2f}% | {item.session_unique_evidence_reduction_pct:.2f}%"
        )
    return rows


if __name__ == "__main__":
    main()
