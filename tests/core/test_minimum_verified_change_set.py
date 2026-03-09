from __future__ import annotations

import pytest

from suitcode.core.change_models import ChangeTarget
from suitcode.core.minimum_verified_change_set_models import (
    MinimumVerifiedChangeSet,
    MinimumVerifiedEvidenceEdge,
    MinimumVerifiedEvidenceEdgeKind,
    MinimumVerifiedQualityOperation,
    QualityOperationKind,
    QualityOperationScope,
)
from suitcode.core.provenance_builders import heuristic_provenance
from suitcode.core.workspace import Workspace


def test_minimum_verified_change_set_for_npm_file_target(npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="packages/core/src/index.ts")
    )

    assert change_set.target_kind == "file"
    assert change_set.owner.id == "component:npm:@monorepo/core"
    assert change_set.primary_component is not None
    assert change_set.primary_component.id == "component:npm:@monorepo/core"
    assert [item.target.test_definition.id for item in change_set.tests] == ["test:npm:@monorepo/core"]
    assert change_set.build_targets == tuple()
    assert change_set.runner_actions == tuple()
    assert len(change_set.quality_validation_operations) == 1
    assert len(change_set.quality_hygiene_operations) == 1
    assert change_set.quality_validation_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.quality_hygiene_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.tests[0].proof_edges[0].edge_kind == MinimumVerifiedEvidenceEdgeKind.TARGET_TEST_TARGET
    assert change_set.quality_validation_operations[0].proof_edges[0].edge_kind == (
        MinimumVerifiedEvidenceEdgeKind.TARGET_QUALITY_VALIDATION
    )
    assert change_set.provenance


def test_minimum_verified_change_set_for_npm_runner_owner(npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(owner_id="runner:npm:@monorepo/codegen:test")
    )

    assert change_set.target_kind == "owner"
    assert change_set.owner.id == "runner:npm:@monorepo/codegen:test"
    assert [item.action.id for item in change_set.runner_actions] == ["action:npm:runner:@monorepo/codegen:test"]
    assert change_set.runner_actions[0].proof_edges[0].edge_kind == (
        MinimumVerifiedEvidenceEdgeKind.TARGET_RUNNER_ACTION
    )
    assert change_set.quality_validation_operations == tuple()
    assert change_set.provenance


def test_minimum_verified_change_set_for_python_owner_target(python_repo_root) -> None:
    repository = Workspace(python_repo_root).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(owner_id="component:python:acme")
    )

    assert change_set.target_kind == "owner"
    assert change_set.owner.id == "component:python:acme"
    assert change_set.primary_component is not None
    assert change_set.primary_component.id == "component:python:acme"
    assert [item.target.action_id for item in change_set.build_targets] == ["action:python:build:repository"]
    assert sorted(item.target.test_definition.id for item in change_set.tests) == [
        "test:python:pytest:root",
        "test:python:unittest:root",
    ]
    assert change_set.quality_validation_operations[0].repository_rel_paths == (
        "src/acme/__init__.py",
        "src/acme/core/__init__.py",
        "src/acme/core/models/__init__.py",
        "src/acme/core/repository.py",
        "src/acme/mcp/__init__.py",
        "src/acme/providers/__init__.py",
    )
    assert change_set.provenance


def test_minimum_verified_quality_operation_validates_contract() -> None:
    provenance = (
        heuristic_provenance(
            evidence_summary="test provenance",
            evidence_paths=("src/app.py",),
        ),
    )
    proof = (
        MinimumVerifiedEvidenceEdge(
            source_node_kind="change_target",
            source_node_id="change_target:file:src/app.py",
            target_node_kind="quality_operation",
            target_node_id="quality_op:python:lint",
            edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_QUALITY_VALIDATION,
            reason="lint applies",
            provenance=provenance,
        ),
    )

    with pytest.raises(ValueError):
        MinimumVerifiedQualityOperation(
            id="quality_op:python:lint",
            provider_id="python",
            operation=QualityOperationKind.LINT,
            scope=QualityOperationScope.VALIDATION,
            repository_rel_paths=("src/app.py",),
            mcp_tool_name="lint_file",
            is_fix=True,
            is_mutating=False,
            inclusion_reason="lint applies",
            inclusion_confidence_mode="heuristic",
            proof_edges=proof,
            provenance=provenance,
        )


def test_minimum_verified_change_set_requires_at_least_one_surface() -> None:
    provenance = (
        heuristic_provenance(
            evidence_summary="test provenance",
            evidence_paths=("src/app.py",),
        ),
    )
    with pytest.raises(ValueError):
        MinimumVerifiedChangeSet(
            target_kind="file",
            owner={"id": "component:python:app", "kind": "component", "name": "app"},
            tests=tuple(),
            build_targets=tuple(),
            runner_actions=tuple(),
            quality_validation_operations=tuple(),
            quality_hygiene_operations=tuple(),
            excluded_items=tuple(),
            provenance=provenance,
        )
