from __future__ import annotations

from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget

__all__ = ["RelatedTestMatch", "RelatedTestTarget", "TestIntelligence"]


def __getattr__(name: str):
    if name == "TestIntelligence":
        from suitcode.core.tests.test_intelligence import TestIntelligence

        return TestIntelligence
    raise AttributeError(name)
