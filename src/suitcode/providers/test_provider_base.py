from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, RelatedTestTarget
from suitcode.providers.provider_base import ProviderBase

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
