from __future__ import annotations

import pytest

from suitcode.core.action_models import ActionKind, ActionQuery


def test_repository_lists_actions_with_provenance(npm_repository) -> None:
    actions = npm_repository.list_actions()

    assert actions
    assert all(item.provenance for item in actions)
    assert any(item.kind == ActionKind.RUNNER_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.TEST_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.BUILD_EXECUTION for item in actions)


def test_repository_lists_actions_for_exact_component(npm_repository) -> None:
    component_id = "component:npm:@monorepo/core"
    actions = npm_repository.list_actions(ActionQuery(component_id=component_id))

    assert actions
    assert all(component_id in item.owner_ids or item.target_id == component_id for item in actions)


def test_repository_lists_actions_for_file_owner(npm_repository) -> None:
    actions = npm_repository.list_actions(ActionQuery(repository_rel_path="packages/core/src/index.ts"))

    assert actions
    assert all("component:npm:@monorepo/core" in item.owner_ids for item in actions)


def test_repository_lists_actions_for_exact_runner(npm_repository) -> None:
    all_actions = npm_repository.list_actions()
    runner_action = next(item for item in all_actions if item.kind == ActionKind.RUNNER_EXECUTION)

    actions = npm_repository.list_actions(ActionQuery(runner_id=runner_action.target_id))

    assert actions
    assert all(item.target_id == runner_action.target_id for item in actions)


def test_action_query_fails_for_multiple_selectors() -> None:
    with pytest.raises(ValueError):
        ActionQuery(owner_id="component:npm:@monorepo/core", repository_rel_path="packages/core/src/index.ts")


def test_repository_action_query_fails_for_unknown_runner(npm_repository) -> None:
    with pytest.raises(ValueError):
        npm_repository.list_actions(ActionQuery(runner_id="runner:npm:missing:test"))
