from __future__ import annotations

from suitcode.core.tests.models import (
    DiscoveredTestDefinition,
    RelatedTestMatch,
    RelatedTestTarget,
    ResolvedRelatedTest,
    TestExecutionResult,
    TestExecutionStatus,
    TestDiscoveryMethod,
    TestFailureSnippet,
    TestTargetDescription,
)

__all__ = [
    "DiscoveredTestDefinition",
    "RelatedTestMatch",
    "RelatedTestTarget",
    "ResolvedRelatedTest",
    "TestExecutionResult",
    "TestExecutionStatus",
    "TestDiscoveryMethod",
    "TestFailureSnippet",
    "TestTargetDescription",
    "TestIntelligence",
]


def __getattr__(name: str):
    if name == "TestIntelligence":
        from suitcode.core.tests.test_intelligence import TestIntelligence

        return TestIntelligence
    raise AttributeError(name)
