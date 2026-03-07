from __future__ import annotations

import pytest

from suitcode.core.action_models import (
    ActionInvocation,
    ActionKind,
    ActionTargetKind,
    RepositoryAction,
)
from suitcode.core.models import TestDefinition as CoreTestDefinition, TestFramework as CoreTestFramework
from suitcode.core.provenance_builders import heuristic_provenance, test_tool_provenance as make_test_tool_provenance
from suitcode.core.tests.models import (
    DiscoveredTestDefinition,
    TestExecutionResult as CoreTestExecutionResult,
    TestExecutionStatus,
)
from suitcode.providers.shared.test_target_runtime import DeterministicTestTargetMixin


class _FakeRepository:
    def __init__(self, actions: tuple[RepositoryAction, ...]) -> None:
        self._actions = actions

    def list_actions(self, query):
        if query.test_id is None:
            return self._actions
        return tuple(action for action in self._actions if action.target_id == query.test_id)


class _FakeExecutionService:
    def run_target(self, description, timeout_seconds: int) -> CoreTestExecutionResult:
        return CoreTestExecutionResult(
            test_id=description.test_definition.id,
            status=TestExecutionStatus.PASSED,
            success=True,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            exit_code=0,
            duration_ms=timeout_seconds,
            log_path=".suit/runs/tests/fake.log",
            warning=description.warning,
            output_excerpt="ok",
            provenance=(
                heuristic_provenance(
                    evidence_summary="fake execution result",
                    evidence_paths=("tests/test_sample.py",),
                ),
            ),
        )


class _FakeRuntime(DeterministicTestTargetMixin):
    PROVIDER_ID = "fake"

    def __init__(
        self,
        discovered_tests: tuple[DiscoveredTestDefinition, ...],
        actions: tuple[RepositoryAction, ...],
    ) -> None:
        self._repository = _FakeRepository(actions)
        self._discovered_tests = discovered_tests
        self._execution = _FakeExecutionService()

    @property
    def repository(self):
        return self._repository

    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        return self._discovered_tests

    def _build_test_execution_service(self):
        return self._execution


def _test_definition(test_id: str) -> CoreTestDefinition:
    return CoreTestDefinition(
        id=test_id,
        name="sample",
        framework=CoreTestFramework.PYTEST,
        test_files=("tests/test_sample.py",),
        provenance=(
            make_test_tool_provenance(
                source_tool="pytest",
                evidence_summary="derived from pytest collect",
                evidence_paths=("tests/test_sample.py",),
            ),
        ),
    )


def _action(test_id: str, action_id_suffix: str = "a") -> RepositoryAction:
    return RepositoryAction(
        id=f"action:fake:test:{action_id_suffix}",
        name="Run sample tests",
        kind=ActionKind.TEST_EXECUTION,
        provider_id="fake",
        target_id=test_id,
        target_kind=ActionTargetKind.TEST_DEFINITION,
        owner_ids=(test_id,),
        invocation=ActionInvocation(argv=("pytest", "tests/test_sample.py"), cwd=None),
        dry_run_supported=True,
        provenance=(
            heuristic_provenance(
                evidence_summary="derived from deterministic action mapping",
                evidence_paths=("pyproject.toml",),
            ),
        ),
    )


def test_describe_test_target_warns_for_heuristic_tests() -> None:
    test_id = "test:fake:heuristic"
    discovered = DiscoveredTestDefinition(
        test_definition=_test_definition(test_id),
        provenance=(
            heuristic_provenance(
                evidence_summary="heuristic test discovery",
                evidence_paths=("tests/test_sample.py",),
            ),
        ),
    )
    runtime = _FakeRuntime((discovered,), (_action(test_id),))

    description = runtime.describe_test_target(test_id)

    assert description.test_definition.id == test_id
    assert description.warning is not None
    assert description.provenance


def test_run_test_targets_executes_valid_batch() -> None:
    test_id = "test:fake:authoritative"
    discovered = DiscoveredTestDefinition(
        test_definition=_test_definition(test_id),
        provenance=(
            make_test_tool_provenance(
                source_tool="pytest",
                evidence_summary="derived from pytest collect",
                evidence_paths=("tests/test_sample.py",),
            ),
        ),
    )
    runtime = _FakeRuntime((discovered,), (_action(test_id),))

    result = runtime.run_test_targets((test_id,), timeout_seconds=12)

    assert result[0].test_id == test_id
    assert result[0].duration_ms == 12


def test_run_test_targets_fails_fast_for_invalid_batch() -> None:
    runtime = _FakeRuntime(tuple(), tuple())
    with pytest.raises(ValueError, match="must not contain duplicates"):
        runtime.run_test_targets(("test:a", "test:a"), timeout_seconds=10)


def test_describe_test_target_fails_for_missing_or_ambiguous_action() -> None:
    test_id = "test:fake:missing-action"
    discovered = DiscoveredTestDefinition(
        test_definition=_test_definition(test_id),
        provenance=(
            make_test_tool_provenance(
                source_tool="pytest",
                evidence_summary="derived from pytest collect",
                evidence_paths=("tests/test_sample.py",),
            ),
        ),
    )
    missing = _FakeRuntime((discovered,), tuple())
    with pytest.raises(ValueError, match="missing fake test action"):
        missing.describe_test_target(test_id)

    ambiguous = _FakeRuntime((discovered,), (_action(test_id, "a"), _action(test_id, "b")))
    with pytest.raises(ValueError, match="ambiguous fake test actions"):
        ambiguous.describe_test_target(test_id)
