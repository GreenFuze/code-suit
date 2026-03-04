from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.test_provider_base import TestProviderBase


class TestIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[TestProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_role(ProviderRole.TEST)
            if isinstance(provider, TestProviderBase)
        )

    def get_tests(self) -> tuple[TestDefinition, ...]:
        items = [item for provider in self.providers for item in provider.get_tests()]
        return tuple(sorted(items, key=lambda item: item.id))

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        items = [item for provider in self.providers for item in provider.get_related_tests(target)]
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    item.test_definition.id,
                    item.relation_reason,
                    item.matched_owner_id or "",
                    item.matched_repository_rel_path or "",
                ),
            )
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
