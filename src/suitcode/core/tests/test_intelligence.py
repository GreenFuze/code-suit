from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import (
    DiscoveredTestDefinition,
    RelatedTestTarget,
    ResolvedRelatedTest,
    TestExecutionResult,
    TestTargetDescription,
)
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.test_provider_base import TestProviderBase


class TestIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository
        self._provider_index_by_test_id: dict[str, TestProviderBase] | None = None

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

    def describe_test_target(self, test_id: str) -> TestTargetDescription:
        provider = self._provider_for_test_id(test_id)
        description = provider.describe_test_target(test_id)
        if description.test_definition.id != test_id:
            raise ValueError(
                f"provider returned mismatched test target description id: expected `{test_id}`, "
                f"got `{description.test_definition.id}`"
            )
        return description

    def run_test_targets(self, test_ids: tuple[str, ...], timeout_seconds: int = 120) -> tuple[TestExecutionResult, ...]:
        self._validate_batch(test_ids)
        if timeout_seconds < 1 or timeout_seconds > 3600:
            raise ValueError("timeout_seconds must be between 1 and 3600")

        grouped_ids: dict[TestProviderBase, list[str]] = {}
        for test_id in test_ids:
            provider = self._provider_for_test_id(test_id)
            grouped_ids.setdefault(provider, []).append(test_id)

        results_by_id: dict[str, TestExecutionResult] = {}
        for provider, provider_test_ids in grouped_ids.items():
            provider_results = provider.run_test_targets(tuple(provider_test_ids), timeout_seconds=timeout_seconds)
            expected = set(provider_test_ids)
            actual = {item.test_id for item in provider_results}
            if expected != actual:
                raise ValueError(
                    f"provider returned unexpected test run results: expected `{sorted(expected)}`, got `{sorted(actual)}`"
                )
            for item in provider_results:
                if item.test_id in results_by_id:
                    raise ValueError(f"duplicate test execution result returned: `{item.test_id}`")
                results_by_id[item.test_id] = item
        return tuple(results_by_id[test_id] for test_id in test_ids)

    def _provider_for_test_id(self, test_id: str) -> TestProviderBase:
        if self._provider_index_by_test_id is None:
            index: dict[str, TestProviderBase] = {}
            for provider in self.providers:
                for discovered in provider.get_discovered_tests():
                    discovered_id = discovered.test_definition.id
                    if discovered_id in index:
                        raise ValueError(f"duplicate test id detected across providers: `{discovered_id}`")
                    index[discovered_id] = provider
            self._provider_index_by_test_id = index
        try:
            return self._provider_index_by_test_id[test_id]
        except KeyError as exc:
            raise ValueError(f"unknown test id: `{test_id}`") from exc

    @staticmethod
    def _validate_batch(test_ids: tuple[str, ...]) -> None:
        if not test_ids:
            raise ValueError("test_ids must not be empty")
        if len(test_ids) > 25:
            raise ValueError("test_ids must not contain more than 25 items")
        if any(not item.strip() for item in test_ids):
            raise ValueError("test_ids must not contain empty values")
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("test_ids must not contain duplicates")


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
