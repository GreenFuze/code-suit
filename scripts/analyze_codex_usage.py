from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.codex_analytics_service import CodexAnalyticsService
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_codex_usage")
    parser.add_argument("--repository-root", type=str, default=None)
    parser.add_argument("--session-id", type=str, default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--include-correlation", action="store_true")
    parser.add_argument("--include-tokens", action="store_true")
    parser.add_argument("--show-segments", action="store_true")
    parser.add_argument("--segment-limit", type=int, default=50)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def build_service(include_correlation: bool, include_tokens: bool) -> CodexAnalyticsService:
    codex_store = CodexSessionStore()
    capture_builder = CodexTranscriptCaptureBuilder()
    token_estimator = TranscriptTokenEstimator() if include_tokens else None
    if not include_correlation:
        return CodexAnalyticsService(
            codex_store,
            capture_builder=capture_builder,
            token_estimator=token_estimator,
        )
    analytics_store = JsonlAnalyticsStore(AnalyticsSettings.from_env())
    correlation = AnalyticsCorrelationService(analytics_store)
    return CodexAnalyticsService(
        codex_store,
        correlation_service=correlation,
        capture_builder=capture_builder,
        token_estimator=token_estimator,
    )


def _session_payload(item, *, include_tokens: bool) -> dict[str, object]:
    exclude: set[str] = set()
    if not include_tokens:
        exclude.add("transcript_capture")
        exclude.add("token_breakdown")
    return item.model_dump(mode="json", exclude=exclude)


def main() -> None:
    args = build_parser().parse_args()
    repository_root = Path(args.repository_root).expanduser().resolve() if args.repository_root else None
    if args.limit <= 0:
        raise ValueError("--limit must be > 0")
    if args.segment_limit <= 0:
        raise ValueError("--segment-limit must be > 0")
    if args.show_segments and not args.include_tokens:
        raise ValueError("--show-segments requires --include-tokens")

    service = build_service(args.include_correlation, args.include_tokens)

    if args.latest:
        session = service.latest_repository_session(repository_root) if repository_root is not None else None
        sessions = tuple([session] if session is not None else [])
        summary = service.repository_summary(repository_root)
    elif args.session_id is not None:
        sessions = service.session_analytics(repository_root=repository_root, session_id=args.session_id)
        summary = service.repository_summary(repository_root)
    else:
        sessions = service.session_analytics(repository_root=repository_root)[: args.limit]
        summary = service.repository_summary(repository_root)

    if args.as_json:
        payload = {
            "filters": {
                "repository_root": (str(repository_root) if repository_root is not None else None),
                "session_id": args.session_id,
                "latest": args.latest,
                "include_correlation": args.include_correlation,
                "include_tokens": args.include_tokens,
                "show_segments": args.show_segments,
                "segment_limit": args.segment_limit,
                "limit": args.limit,
            },
            "summary": summary.model_dump(mode="json"),
            "sessions": [_session_payload(item, include_tokens=args.include_tokens) for item in sessions],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Codex SuitCode Usage")
    print("====================")
    print(f"Repository root filter: {repository_root or '(none)'}")
    print(f"Session filter: {args.session_id or '(none)'}")
    print(f"Latest only: {args.latest}")
    print(f"Correlation enabled: {args.include_correlation}")
    print(f"Token estimation enabled: {args.include_tokens}")
    print()
    print(f"Session count: {summary.session_count}")
    print(f"Sessions using SuitCode: {summary.sessions_using_suitcode}")
    print(f"Sessions without SuitCode: {summary.sessions_without_suitcode}")
    print(f"Sessions without high-value SuitCode: {summary.sessions_without_high_value_suitcode}")
    print(f"Late SuitCode adoption sessions: {summary.sessions_with_late_suitcode_adoption}")
    print(f"Late high-value SuitCode adoption sessions: {summary.sessions_with_late_high_value_adoption}")
    print(f"Shell-heavy before SuitCode sessions: {summary.sessions_with_shell_heavy_pre_suitcode}")
    print(f"Skipped artifacts: {summary.skipped_artifacts}")
    print(f"Latest session: {summary.latest_session_id or '(none)'}")
    print(f"Latest session at: {summary.latest_session_at or '(none)'}")
    print(f"First tool distribution: {summary.first_tool_distribution or {}}")
    print(f"First high-value tool distribution: {summary.first_high_value_tool_distribution or {}}")
    print(
        "Average first-tool positions: "
        f"suitcode={summary.avg_first_suitcode_tool_index if summary.avg_first_suitcode_tool_index is not None else '(none)'}, "
        f"high_value={summary.avg_first_high_value_suitcode_tool_index if summary.avg_first_high_value_suitcode_tool_index is not None else '(none)'}"
    )
    print(f"Correlation quality mix: {summary.correlation_quality_mix or {}}")
    print(
        "Transcript metrics: "
        f"events={summary.transcript_metrics.event_count}, "
        f"tool_calls={summary.transcript_metrics.tool_event_count}, "
        f"mcp_calls={summary.transcript_metrics.mcp_tool_call_count}, "
        f"suitcode_calls={summary.transcript_metrics.suitcode_tool_call_count}"
    )
    if args.include_tokens:
        print(
            "Transcript tokens: "
            f"total={summary.total_tokens if summary.total_tokens is not None else '(none)'}, "
            f"avg_per_session={summary.avg_tokens_per_session if summary.avg_tokens_per_session is not None else '(none)'}, "
            f"avg_before_first_suitcode={summary.avg_tokens_before_first_suitcode_tool if summary.avg_tokens_before_first_suitcode_tool is not None else '(none)'}, "
            f"avg_before_first_high_value={summary.avg_tokens_before_first_high_value_suitcode_tool if summary.avg_tokens_before_first_high_value_suitcode_tool is not None else '(none)'}"
        )
        print(f"Token breakdowns: {summary.token_breakdowns_by_kind or {}}")
    print()
    print("Top SuitCode tools")
    print("------------------")
    if not summary.tool_usage:
        print("(none)")
    for item in summary.tool_usage:
        print(f"{item.tool_name}: calls={item.call_count}, first={item.first_seen_at}, last={item.last_seen_at}")
    print()
    print("Sessions")
    print("--------")
    if not sessions:
        print("(none)")
    for item in sessions:
        print(
            f"{item.session_id}: used_suitcode={item.used_suitcode}, "
            f"first_tool={item.first_suitcode_tool or '-'}@{item.first_suitcode_tool_index or '-'}, "
            f"first_high_value={item.first_high_value_suitcode_tool or '-'}@{item.first_high_value_suitcode_tool_index or '-'}, "
            f"late_suitcode={item.late_suitcode_adoption}, "
            f"late_high_value={item.late_high_value_suitcode_adoption}, "
            f"no_high_value={item.used_no_high_value_suitcode_tool}, "
            f"shell_heavy={item.shell_heavy_before_suitcode}, "
            f"correlation={item.correlation_quality.value}, "
            f"artifact={item.artifact.artifact_path}"
        )
        if args.include_tokens and item.token_breakdown is not None:
            print(
                f"  tokens: total={item.token_breakdown.total_tokens}, "
                f"before_first_suitcode={item.token_breakdown.tokens_before_first_suitcode_tool}, "
                f"before_first_high_value={item.token_breakdown.tokens_before_first_high_value_suitcode_tool}, "
                f"first_high_value={item.token_breakdown.first_high_value_suitcode_tool or '-'}"
            )
            if args.show_segments and item.transcript_capture is not None:
                for segment in item.transcript_capture.segments[: args.segment_limit]:
                    tool_name = f", tool={segment.tool_name}" if segment.tool_name is not None else ""
                    print(
                        f"  [{segment.sequence_index}] {segment.kind.value}{tool_name}: "
                        f"{segment.content_text!r}"
                    )
    if summary.notes:
        print()
        print("Notes")
        print("-----")
        for note in summary.notes:
            print(f"- {note}")


if __name__ == "__main__":
    main()
