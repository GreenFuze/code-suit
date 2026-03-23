from __future__ import annotations

from suitcode.analytics.codex_usage_policy import with_usage_flags
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.cursor_session_parser import CursorSessionParser
from suitcode.analytics.cursor_session_store import CursorSessionStore
from suitcode.analytics.cursor_transcript_capture import CursorTranscriptCaptureBuilder
from suitcode.analytics.native_analytics_service import NativeAnalyticsService
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator


class CursorAnalyticsService(NativeAnalyticsService):
    def __init__(
        self,
        store: CursorSessionStore,
        *,
        parser: CursorSessionParser | None = None,
        correlation_service: AnalyticsCorrelationService | None = None,
        capture_builder: CursorTranscriptCaptureBuilder | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
    ) -> None:
        cursor_store = store
        super().__init__(
            cursor_store,
            parser=parser or CursorSessionParser(cursor_store),
            correlation_service=correlation_service,
            capture_builder=capture_builder or CursorTranscriptCaptureBuilder(cursor_store),
            token_estimator=token_estimator,
            usage_policy=with_usage_flags,
        )
