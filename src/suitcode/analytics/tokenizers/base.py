from __future__ import annotations

from abc import ABC, abstractmethod

from suitcode.analytics.native_agent_models import NativeAgentKind
from suitcode.analytics.transcript_models import TranscriptSegment


class TranscriptTokenizer(ABC):
    @property
    @abstractmethod
    def model_family(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def supports(self, agent_kind: NativeAgentKind, model_provider: str | None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def count_text(self, text: str) -> int:
        raise NotImplementedError

    def count_segment(self, segment: TranscriptSegment) -> int:
        return self.count_text(segment.content_text)
