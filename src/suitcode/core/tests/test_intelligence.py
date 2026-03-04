from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestTarget, ResolvedRelatedTest
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
        return tuple(item.test_definition for item in self.get_discovered_tests())

    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        items = [item for provider in self.providers for item in provider.get_discovered_tests()]
        by_id: dict[str, DiscoveredTestDefinition] = {}
        for item in items:
            if item.test_definition.id in by_id:
                raise ValueError(f"duplicate test id detected across providers: `{item.test_definition.id}`")
            by_id[item.test_definition.id] = item
        return tuple(sorted(by_id.values(), key=lambda item: item.test_definition.id))

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[ResolvedRelatedTest, ...]:
        discovered_tests = {item.test_definition.id: item for item in self.get_discovered_tests()}
        items: list[ResolvedRelatedTest] = []
        for provider in self.providers:
            for match in provider.get_related_tests(target):
                try:
                    discovered_test = discovered_tests[match.test_definition.id]
                except KeyError as exc:
                    raise ValueError(
                        f"related test `{match.test_definition.id}` has no discovered test metadata"
                    ) from exc
                items.append(ResolvedRelatedTest(match=match, discovered_test=discovered_test))
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    item.match.test_definition.id,
                    item.match.relation_reason,
                    item.match.matched_owner_id or "",
                    item.match.matched_repository_rel_path or "",
                ),
            )
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
