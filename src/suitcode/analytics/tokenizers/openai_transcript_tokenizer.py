from __future__ import annotations

import tiktoken

from suitcode.analytics.native_agent_models import NativeAgentKind
from suitcode.analytics.tokenizers.base import TranscriptTokenizer


class OpenAiTranscriptTokenizer(TranscriptTokenizer):
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._model_family = "openai/codex"

    @property
    def model_family(self) -> str:
        return self._model_family

    def supports(self, agent_kind: NativeAgentKind, model_provider: str | None) -> bool:
        return agent_kind == NativeAgentKind.CODEX and (model_provider is None or model_provider == "openai")

    def count_text(self, text: str) -> int:
        return len(self._encoding.encode(text))
