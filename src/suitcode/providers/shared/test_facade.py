from __future__ import annotations

from abc import abstractmethod
from threading import Lock

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition


class TestFacadeMixin:
    def get_tests(self) -> tuple[TestDefinition, ...]:
        return tuple(item.test_definition for item in self.get_discovered_tests())

    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        cached = getattr(self, "_discovered_tests_cache", None)
        if cached is not None:
            return cached
        lock = getattr(self, "_discovered_tests_lock", None)
        if lock is None:
            lock = Lock()
            setattr(self, "_discovered_tests_lock", lock)
        with lock:
            cached = getattr(self, "_discovered_tests_cache", None)
            if cached is not None:
                return cached
            cached = tuple(
                sorted(
                    (self._to_discovered_test_definition(item) for item in self._get_tests_internal()),
                    key=lambda item: item.test_definition.id,
                )
            )
            setattr(self, "_discovered_tests_cache", cached)
            return cached

    @abstractmethod
    def _get_tests_internal(self) -> tuple[object, ...]:
        raise NotImplementedError

    @abstractmethod
    def _to_discovered_test_definition(self, test_analysis: object) -> DiscoveredTestDefinition:
        raise NotImplementedError
