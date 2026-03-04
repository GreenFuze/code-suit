from __future__ import annotations

from enum import StrEnum


class ProviderRole(StrEnum):
    ARCHITECTURE = "architecture"
    CODE = "code"
    TEST = "test"
    QUALITY = "quality"
