from __future__ import annotations

from suitcode.analytics.claude_session_parser import ClaudeSessionParser
from suitcode.analytics.claude_session_store import ClaudeSessionStore
from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder
from suitcode.analytics.codex_usage_policy import with_usage_flags
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.native_analytics_service import NativeAnalyticsService
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


class ClaudeAnalyticsService(NativeAnalyticsService):
    def __init__(
        self,
        store: ClaudeSessionStore,
        *,
        parser: ClaudeSessionParser | None = None,
        correlation_service: AnalyticsCorrelationService | None = None,
        capture_builder: ClaudeTranscriptCaptureBuilder | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
    ) -> None:
        super().__init__(
            store,
            parser=parser or ClaudeSessionParser(),
            correlation_service=correlation_service,
            capture_builder=capture_builder,
            token_estimator=token_estimator,
            usage_policy=with_usage_flags,
        )
