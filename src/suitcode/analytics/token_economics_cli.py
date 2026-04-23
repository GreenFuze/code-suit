from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from suitcode.analytics.token_economics import (
    TokenEconomicsArtifactSet,
    TokenEconomicsReport,
    generate_token_economics_report,
    write_token_economics_report_artifacts,
)


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
    parser.add_argument(
        "--codex-transcript",
        default=None,
        help="Optional Codex session JSONL transcript used for deterministic task-level token estimates.",
    )
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--task-id",
        default=None,
        help="Restrict correlated token-economics events to this SUITCODE_TASK_ID after transcript-window filtering.",
    )
    scope_group.add_argument(
        "--analytics-session-id",
        default=None,
        help="Restrict correlated token-economics events to this SuitCode analytics session after transcript-window filtering.",
    )
    parser.add_argument(
        "--analytics-run-id",
        default=None,
        help="Restrict events to this SuitCode analytics run id.",
    )
    parser.add_argument(
        "--experiment-id",
        default=None,
        help="Restrict events to this experiment id from the analytics run manifest.",
    )
    parser.add_argument(
        "--transcript-window-padding-seconds",
        type=int,
        default=300,
        help="Padding applied before/after the transcript time window when correlating SuitCode events. Defaults to 300.",
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Persist a paired JSON and Markdown lab-report artifact set under .suit/analytics/reports/.",
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
        ignore_analytics_run_ids=set(ignore.get("analytics_run_ids", [])),
        ignore_transcript_artifact_paths=set(ignore.get("transcript_artifact_paths", [])),
        ignore_reason_labels=set(ignore.get("reason_labels", [])),
        task_id=args.task_id,
        analytics_session_id=args.analytics_session_id,
        analytics_run_id=args.analytics_run_id,
        experiment_id=args.experiment_id,
        codex_transcript_path=(Path(args.codex_transcript) if args.codex_transcript else None),
        transcript_window_padding_seconds=args.transcript_window_padding_seconds,
    )
    artifacts: TokenEconomicsArtifactSet | None = None
    if args.write_artifacts:
        artifacts = write_token_economics_report_artifacts(workspace, report)
    if args.json:
        payload = report.model_dump(mode="json")
        if artifacts is not None:
            payload["artifacts"] = artifacts.model_dump(mode="json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(_format_text_report(report, artifacts))


def _load_ignore_file(workspace: Path, ignore_file: str | None) -> dict[str, list[str]]:
    candidate = Path(ignore_file) if ignore_file is not None else _default_ignore_file(workspace)
    if candidate is None or not candidate.exists():
        return {
            "session_ids": [],
            "tool_call_ids": [],
            "analytics_run_ids": [],
            "transcript_artifact_paths": [],
            "reason_labels": [],
        }
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    parsed = {
        "session_ids": _string_list(payload.get("session_ids")),
        "tool_call_ids": _string_list(payload.get("tool_call_ids")),
        "analytics_run_ids": _string_list(payload.get("analytics_run_ids")),
        "transcript_artifact_paths": [str(Path(item).expanduser().resolve()) for item in _string_list(payload.get("transcript_artifact_paths"))],
        "reason_labels": [],
    }
    exclusions = payload.get("exclusions")
    if exclusions is not None:
        if not isinstance(exclusions, list):
            raise ValueError("ignore file `exclusions` must be a list when present")
        for item in exclusions:
            if not isinstance(item, dict):
                raise ValueError("ignore file exclusions must be objects")
            kind = item.get("kind")
            value = item.get("value")
            reason = item.get("reason")
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError("ignore file exclusions require a non-empty `kind`")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("ignore file exclusions require a non-empty `value`")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("ignore file exclusions require a non-empty `reason`")
            normalized_value = value.strip()
            parsed["reason_labels"].append(reason.strip())
            if kind == "session_id":
                parsed["session_ids"].append(normalized_value)
            elif kind == "tool_call_id":
                parsed["tool_call_ids"].append(normalized_value)
            elif kind == "analytics_run_id":
                parsed["analytics_run_ids"].append(normalized_value)
            elif kind == "transcript_artifact_path":
                parsed["transcript_artifact_paths"].append(str(Path(normalized_value).expanduser().resolve()))
            else:
                raise ValueError(f"unsupported ignore exclusion kind: `{kind}`")
    return {
        "session_ids": sorted(set(parsed["session_ids"])),
        "tool_call_ids": sorted(set(parsed["tool_call_ids"])),
        "analytics_run_ids": sorted(set(parsed["analytics_run_ids"])),
        "transcript_artifact_paths": sorted(set(parsed["transcript_artifact_paths"])),
        "reason_labels": sorted(set(parsed["reason_labels"])),
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


def _format_text_report(report: TokenEconomicsReport, artifacts: TokenEconomicsArtifactSet | None = None) -> str:
    lines = [
        "SuitCode Token Economics Report",
        f"Workspace: {report.workspace}",
        f"Generated at: {report.generated_at}",
        f"Failure policy: {'included' if report.filters.include_failures else 'success-only'}",
        f"Ignored events: {report.ignored_event_count}",
        f"Analytics runs: {', '.join(report.matched_analytics_run_ids) if report.matched_analytics_run_ids else 'none'}",
        "",
        _aggregate_line("Total", report.total),
        "",
        _transcript_line(report.total),
        "",
        "By experiment:",
        *_aggregate_table(report.by_experiment),
        "",
        "By analytics run:",
        *_aggregate_table(report.by_analytics_run),
        "",
        "By task kind:",
        *_aggregate_table(report.by_task_kind),
        "",
        "By study kind:",
        *_aggregate_table(report.by_study_kind),
        "",
        "By day:",
        *_aggregate_table(report.by_day),
        "",
        "By tool:",
        *_aggregate_table(report.by_tool),
        "",
        "By session:",
        *_aggregate_table(report.by_session),
        "",
        "By detail level:",
        *_aggregate_table(report.by_detail_level),
        "",
        "By target-count bucket:",
        *_aggregate_table(report.by_target_count_bucket),
        "",
        "By language family:",
        *_aggregate_table(report.by_language_family),
        "",
        "Slowest calls:",
        *_slow_call_table(report.slowest_calls),
        "",
        "Slowest targets:",
        *_slow_target_table(report.slowest_targets),
        "",
        "Dominant stage counts:",
        *_dominant_stage_lines(report.dominant_stage_counts),
    ]
    if report.interpretation_notes:
        lines.extend(["", "Interpretation notes:", *(f"  - {note}" for note in report.interpretation_notes)])
    if artifacts is not None:
        lines.extend(["", f"Artifacts: {artifacts.artifact_root}"])
    return "\n".join(lines)


def _aggregate_line(label: str, item) -> str:
    return (
        f"{label}: calls={item.event_count} success={item.success_count} failures={item.failure_count} "
        f"unfinished={item.unfinished_count} interrupted={item.interrupted_count} degraded={item.degraded_count} fallback={item.fallback_count} retries={item.retrying_call_count} "
        f"avg_ms={item.avg_elapsed_ms:.2f} p50_ms={item.p50_elapsed_ms} "
        f"p95_ms={item.p95_elapsed_ms} max_ms={item.max_elapsed_ms} "
        f"response_tokens={item.total_response_tokens} evidence_tokens={item.total_evidence_footprint_tokens} "
        f"unique_evidence_tokens={item.unique_evidence_tokens} "
        f"evidence_reduction={item.evidence_token_reduction_pct:.2f}% "
        f"unique_evidence_reduction={item.session_unique_evidence_reduction_pct:.2f}% "
        f"expansion_factor={_format_optional_float(item.suitcode_evidence_expansion_factor)} "
        f"response_based_reduction={_format_optional_pct(item.estimated_task_token_reduction_pct_response_based)} "
        f"evidence_lower_bound_reduction={_format_optional_pct(item.estimated_task_token_reduction_pct_evidence_lower_bound)}"
    )


def _aggregate_table(items) -> list[str]:
    if not items:
        return ["  (no events)"]
    rows = [
        "  name | calls | unfinished | interrupted | failures | degraded | fallback | retries | avg_ms | p50_ms | p95_ms | max_ms | response_tokens | evidence_tokens | unique_evidence_tokens | evidence_reduction | unique_reduction | expansion_factor | response_based_reduction | evidence_lower_bound_reduction"
    ]
    for item in items:
        rows.append(
            "  "
            f"{item.name} | {item.event_count} | {item.unfinished_count} | {item.interrupted_count} | {item.failure_count} | "
            f"{item.degraded_count} | {item.fallback_count} | {item.retrying_call_count} | "
            f"{item.avg_elapsed_ms:.2f} | {item.p50_elapsed_ms} | {item.p95_elapsed_ms} | {item.max_elapsed_ms} | "
            f"{item.total_response_tokens} | "
            f"{item.total_evidence_footprint_tokens} | {item.unique_evidence_tokens} | "
            f"{item.evidence_token_reduction_pct:.2f}% | {item.session_unique_evidence_reduction_pct:.2f}% | "
            f"{_format_optional_float(item.suitcode_evidence_expansion_factor)} | "
            f"{_format_optional_pct(item.estimated_task_token_reduction_pct_response_based)} | "
            f"{_format_optional_pct(item.estimated_task_token_reduction_pct_evidence_lower_bound)}"
        )
    return rows


def _transcript_line(item) -> str:
    if item.transcript_session_id is None:
        return "Transcript correlation: none"
    return (
        "Transcript correlation: "
        f"mode={item.correlation_mode} session_id={item.transcript_session_id} "
        f"total_tokens={item.transcript_total_tokens} suitcode_tokens={item.transcript_suitcode_tokens} "
        f"non_suitcode_tokens={item.transcript_non_suitcode_tokens} "
        f"suitcode_calls={item.transcript_suitcode_call_count} matched_calls={item.transcript_correlated_call_count} "
        f"partial={item.transcript_coverage_partial}"
    )


def _slow_call_table(items) -> list[str]:
    if not items:
        return ["  (no calls)"]
    rows = ["  elapsed_ms | tool | status | dominant_stage | targets | tool_call_id"]
    for item in items:
        rows.append(
            "  "
            f"{item.elapsed_ms} | {item.tool_name} | {item.status} | {item.dominant_stage or '-'} | "
            f"{','.join(item.targets) if item.targets else '-'} | {item.tool_call_id}"
        )
    return rows


def _slow_target_table(items) -> list[str]:
    if not items:
        return ["  (no targets)"]
    rows = ["  elapsed_ms | tool | repository_rel_path | status | dominant_stage | tool_call_id"]
    for item in items:
        rows.append(
            "  "
            f"{item.elapsed_ms} | {item.tool_name} | {item.repository_rel_path} | {item.status} | "
            f"{item.dominant_stage or '-'} | {item.tool_call_id}"
        )
    return rows


def _dominant_stage_lines(items: dict[str, int]) -> list[str]:
    if not items:
        return ["  (no timing stages)"]
    return [f"  {name}: {count}" for name, count in items.items()]


def _format_optional_float(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _format_optional_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


if __name__ == "__main__":
    main()
