from __future__ import annotations


class LspError(RuntimeError):
    pass


class LspProtocolError(LspError):
    pass


class LspProcessError(LspError):
    pass
