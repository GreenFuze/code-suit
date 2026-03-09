from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import (
    DiscoveredTestDefinition,
    RelatedTestMatch,
    RelatedTestTarget,
    TestExecutionResult,
    TestTargetDescription,
)
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.runtime_capability_models import TestRuntimeCapabilities

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class TestProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def get_tests(self) -> tuple[TestDefinition, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        raise NotImplementedError

    @abstractmethod
    def describe_test_target(self, test_id: str) -> TestTargetDescription:
        raise NotImplementedError

    @abstractmethod
    def run_test_targets(self, test_ids: tuple[str, ...], timeout_seconds: int) -> tuple[TestExecutionResult, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_test_runtime_capabilities(self) -> TestRuntimeCapabilities:
        raise NotImplementedError
