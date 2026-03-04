from __future__ import annotations

from abc import abstractmethod

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition


class TestFacadeMixin:
    def get_tests(self) -> tuple[TestDefinition, ...]:
        return tuple(item.test_definition for item in self.get_discovered_tests())

    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        return tuple(
            sorted(
                (self._to_discovered_test_definition(item) for item in self._get_tests_internal()),
                key=lambda item: item.test_definition.id,
            )
        )

    @abstractmethod
    def _get_tests_internal(self) -> tuple[object, ...]:
        raise NotImplementedError

    @abstractmethod
    def _to_discovered_test_definition(self, test_analysis: object) -> DiscoveredTestDefinition:
        raise NotImplementedError
