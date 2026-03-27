from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.claude_analytics_service import ClaudeAnalyticsService
from suitcode.analytics.claude_session_store import ClaudeSessionStore
from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.live_usage_filters import parse_cutoff, session_matches_live_filters
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='analyze_claude_usage')
    parser.add_argument('--repository-root', type=str, default=None)
    parser.add_argument('--session-id', type=str, default=None)
    parser.add_argument('--latest', action='store_true')
    parser.add_argument('--include-correlation', action='store_true')
    parser.add_argument('--include-tokens', action='store_true')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--since-utc', type=str, default=None)
    parser.add_argument('--since-hours', type=int, default=None)
    parser.add_argument('--exclude-test-artifacts', action='store_true')
    parser.add_argument('--json', action='store_true', dest='as_json')
    return parser


def build_service(include_correlation: bool, include_tokens: bool) -> ClaudeAnalyticsService:
    store = ClaudeSessionStore()
    capture_builder = ClaudeTranscriptCaptureBuilder()
    token_estimator = TranscriptTokenEstimator() if include_tokens else None
    if not include_correlation:
        return ClaudeAnalyticsService(store, capture_builder=capture_builder, token_estimator=token_estimator)
    analytics_store = JsonlAnalyticsStore(AnalyticsSettings.from_env())
    correlation = AnalyticsCorrelationService(analytics_store)
    return ClaudeAnalyticsService(
        store,
        correlation_service=correlation,
        capture_builder=capture_builder,
        token_estimator=token_estimator,
    )


def _session_payload(item, *, include_tokens: bool) -> dict[str, object]:
    exclude: set[str] = set()
    if not include_tokens:
        exclude.add('transcript_capture')
        exclude.add('token_breakdown')
    return item.model_dump(mode='json', exclude=exclude)


def main() -> None:
    args = build_parser().parse_args()
    repository_root = Path(args.repository_root).expanduser().resolve() if args.repository_root else None
    if args.limit <= 0:
        raise ValueError('--limit must be > 0')

    service = build_service(args.include_correlation, args.include_tokens)
    cutoff = parse_cutoff(since_utc=args.since_utc, since_hours=args.since_hours)
    session_filter = lambda item: session_matches_live_filters(
        item,
        cutoff=cutoff,
        exclude_test_artifacts=args.exclude_test_artifacts,
    )

    if args.latest:
        session = (
            service.latest_repository_session(repository_root, session_filter=session_filter)
            if repository_root is not None
            else None
        )
        sessions = tuple([session] if session is not None else [])
        summary = service.repository_summary(repository_root, session_filter=session_filter)
    elif args.session_id is not None:
        sessions = service.session_analytics(
            repository_root=repository_root,
            session_id=args.session_id,
            session_filter=session_filter,
        )
        summary = service.repository_summary(repository_root, session_filter=session_filter)
    else:
        sessions = service.session_analytics(repository_root=repository_root, session_filter=session_filter)[: args.limit]
        summary = service.repository_summary(repository_root, session_filter=session_filter)

    if args.as_json:
        payload = {
            'filters': {
                'repository_root': (str(repository_root) if repository_root is not None else None),
                'session_id': args.session_id,
                'latest': args.latest,
                'include_correlation': args.include_correlation,
                'include_tokens': args.include_tokens,
                'limit': args.limit,
                'since_utc': args.since_utc,
                'since_hours': args.since_hours,
                'exclude_test_artifacts': args.exclude_test_artifacts,
            },
            'summary': summary.model_dump(mode='json'),
            'sessions': [_session_payload(item, include_tokens=args.include_tokens) for item in sessions],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print('Claude SuitCode Usage')
    print('=====================')
    print(f'Repository root filter: {repository_root or "(none)"}')
    print(f'Session filter: {args.session_id or "(none)"}')
    print(f'Latest only: {args.latest}')
    print(f'Correlation enabled: {args.include_correlation}')
    print(f'Token estimation enabled: {args.include_tokens}')
    print()
    print(f'Session count: {summary.session_count}')
    print(f'Sessions using SuitCode: {summary.sessions_using_suitcode}')
    print(f'Sessions without SuitCode: {summary.sessions_without_suitcode}')
    print(f'First tool distribution: {summary.first_tool_distribution or {}}')
    print(f'Correlation quality mix: {summary.correlation_quality_mix or {}}')
    if args.include_tokens:
        print(f'Transcript tokens: total={summary.total_tokens if summary.total_tokens is not None else "(none)"}')
        if summary.native_reported_input_tokens is not None:
            print(
                'Native-reported tokens: '
                f'input={summary.native_reported_input_tokens}, '
                f'output={summary.native_reported_output_tokens}, '
                f'cache_creation={summary.native_reported_cache_creation_tokens}, '
                f'cache_read={summary.native_reported_cache_read_tokens}'
            )
    print()
    if not sessions:
        print('(none)')
    for item in sessions:
        print(
            f'{item.session_id}: used_suitcode={item.used_suitcode}, '
            f'first_tool={item.first_suitcode_tool or "-"}@{item.first_suitcode_tool_index or "-"}, '
            f'correlation={item.correlation_quality.value}, '
            f'artifact={item.artifact.artifact_path}'
        )


if __name__ == '__main__':
    main()
