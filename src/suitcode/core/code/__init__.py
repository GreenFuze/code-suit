from __future__ import annotations

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget

__all__ = ["CodeIntelligence", "CodeLocation", "SymbolLookupTarget"]


def __getattr__(name: str):
    if name == "CodeIntelligence":
        from suitcode.core.code.code_intelligence import CodeIntelligence

        return CodeIntelligence
    raise AttributeError(name)
