from __future__ import annotations

from suitcode.providers.shared.lsp_code import LspEntityTranslatorBase


class PythonSymbolTranslator(LspEntityTranslatorBase):
    def __init__(self) -> None:
        super().__init__(
            source_tool="basedpyright",
            evidence_summary="discovered from Python LSP symbol information",
        )
