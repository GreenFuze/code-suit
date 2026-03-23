from __future__ import annotations

from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.codex_session_parser import CodexSessionParser
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_usage_policy import with_usage_flags
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.native_analytics_service import NativeAnalyticsService
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


class CodexAnalyticsService(NativeAnalyticsService):
    def __init__(
        self,
        store: CodexSessionStore,
        *,
        parser: CodexSessionParser | None = None,
        correlation_service: AnalyticsCorrelationService | None = None,
        capture_builder: CodexTranscriptCaptureBuilder | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
    ) -> None:
        super().__init__(
            store,
            parser=parser or CodexSessionParser(),
            correlation_service=correlation_service,
            capture_builder=capture_builder,
            token_estimator=token_estimator,
            usage_policy=with_usage_flags,
        )
