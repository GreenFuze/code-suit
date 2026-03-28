from __future__ import annotations

from suitcode.providers.shared.lsp_code import LspEntityTranslatorBase


class GoSymbolTranslator(LspEntityTranslatorBase):
    def __init__(self) -> None:
        super().__init__(
            source_tool="gopls",
            evidence_summary="discovered from Go LSP symbol information",
        )
