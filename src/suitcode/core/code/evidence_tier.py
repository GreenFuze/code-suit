from __future__ import annotations

from enum import StrEnum


class CodeEvidenceTier(StrEnum):
    __test__ = False
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
