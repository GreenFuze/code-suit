from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.action_models import ActionKind, ActionQuery, RepositoryAction
from suitcode.core.tests.models import DiscoveredTestDefinition, TestExecutionResult, TestTargetDescription

if TYPE_CHECKING:
    from suitcode.providers.shared.test_execution import TestExecutionService


class DeterministicTestTargetMixin:
    PROVIDER_ID: str

    @abstractmethod
    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        raise NotImplementedError

    @abstractmethod
    def _build_test_execution_service(self) -> TestExecutionService:
        raise NotImplementedError

    def describe_test_target(self, test_id: str) -> TestTargetDescription:
        discovered = self._discovered_test_by_id(test_id)
        action = self._test_action_for_id(test_id)
        warning = None
        if not discovered.is_authoritative:
            warning = "Test target scope is heuristic; command is deterministic but may include tests beyond exact ownership."
        return TestTargetDescription(
            test_definition=discovered.test_definition,
            command_argv=action.invocation.argv,
            command_cwd=action.invocation.cwd,
            is_authoritative=discovered.is_authoritative,
            warning=warning,
            provenance=(*discovered.provenance, *action.provenance),
        )

    def run_test_targets(self, test_ids: tuple[str, ...], timeout_seconds: int) -> tuple[TestExecutionResult, ...]:
        self._validate_test_id_batch(test_ids)
        if timeout_seconds < 1 or timeout_seconds > 3600:
            raise ValueError("timeout_seconds must be between 1 and 3600")
        execution_service = self._build_test_execution_service()
        return tuple(
            execution_service.run_target(self.describe_test_target(test_id), timeout_seconds=timeout_seconds)
            for test_id in test_ids
        )

    def _discovered_test_by_id(self, test_id: str) -> DiscoveredTestDefinition:
        for discovered in self.get_discovered_tests():
            if discovered.test_definition.id == test_id:
                return discovered
        raise ValueError(f"unknown {self.PROVIDER_ID} test id: `{test_id}`")

    def _test_action_for_id(self, test_id: str) -> RepositoryAction:
        actions = tuple(
            action
            for action in self.repository.list_actions(ActionQuery(test_id=test_id))
            if action.provider_id == self.PROVIDER_ID and action.kind == ActionKind.TEST_EXECUTION
        )
        if not actions:
            raise ValueError(f"missing {self.PROVIDER_ID} test action for test id `{test_id}`")
        if len(actions) != 1:
            raise ValueError(f"ambiguous {self.PROVIDER_ID} test actions for test id `{test_id}`")
        return actions[0]

    @staticmethod
    def _validate_test_id_batch(test_ids: tuple[str, ...]) -> None:
        if not test_ids:
            raise ValueError("test_ids must not be empty")
        if len(test_ids) > 25:
            raise ValueError("test_ids must not contain more than 25 items")
        if any(not test_id.strip() for test_id in test_ids):
            raise ValueError("test_ids must not contain empty values")
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("test_ids must not contain duplicates")
