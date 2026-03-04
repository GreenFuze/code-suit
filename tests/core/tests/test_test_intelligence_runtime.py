from __future__ import annotations

from pathlib import Path

from suitcode.core.models import TestDefinition as DefinitionNode
from suitcode.core.models.graph_types import TestFramework as FrameworkEnum
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.tests.test_intelligence import TestIntelligence as RuntimeTestIntelligence
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.test_provider_base import TestProviderBase


class _FakeRepository:
    def __init__(self, providers):
        self._providers = providers

    def get_providers_for_role(self, role: ProviderRole):
        if role == ProviderRole.TEST:
            return self._providers
        return tuple()


class _TestProvider(TestProviderBase):
    PROVIDER_ID = "fake-test"
    DISPLAY_NAME = "fake-test"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.TEST})

    def __init__(self, repository, suffix: str) -> None:
        super().__init__(repository)
        self._suffix = suffix

    def get_tests(self):
        return (
            DefinitionNode(
                id=f"test:{self._suffix}",
                name=f"test-{self._suffix}",
                framework=FrameworkEnum.OTHER,
            ),
        )

    def get_related_tests(self, target: RelatedTestTarget):
        return tuple()


def test_test_intelligence_concatenates_and_sorts_definitions() -> None:
    repo = _FakeRepository(
        (
            _TestProvider(repository=None, suffix="b"),  # type: ignore[arg-type]
            _TestProvider(repository=None, suffix="a"),  # type: ignore[arg-type]
        )
    )
    intelligence = RuntimeTestIntelligence(repo)  # type: ignore[arg-type]

    assert tuple(node.id for node in intelligence.get_tests()) == ("test:a", "test:b")
