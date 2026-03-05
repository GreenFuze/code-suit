from __future__ import annotations

from suitcode.providers.shared.lsp_code import LspLocationTranslatorBase


class NpmLocationTranslator(LspLocationTranslatorBase):
    def __init__(self) -> None:
        super().__init__(source_tool="typescript-language-server")
