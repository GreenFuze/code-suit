from __future__ import annotations

from pathlib import Path

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
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, ResolvedRelatedTest
from suitcode.core.workspace import Workspace


def _make_mixed_go_npm_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "server" / "internal" / "db").mkdir(parents=True)
    (repo_root / "server" / "go.mod").write_text(
        "module example.com/mixed/server\n\ngo 1.22\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "internal" / "db" / "repo.go").write_text(
        "package db\n\nfunc Name() string { return \"db\" }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "internal" / "db" / "repo_test.go").write_text(
        "package db\n\nimport \"testing\"\n\nfunc TestName(t *testing.T) { _ = Name() }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src").mkdir(parents=True)
    (repo_root / "server" / "frontend" / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src" / "index.tsx").write_text(
        "export const App = () => null;\n",
        encoding="utf-8",
    )
    return repo_root


def _make_frontend_build_only_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text(
        "export const App = () => null;\n",
        encoding="utf-8",
    )
    return repo_root


def _make_frontend_artifact_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "public" / "runtimes").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "main": "public/runtimes/index.js",
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text(
        "export const App = () => null;\n",
        encoding="utf-8",
    )
    (repo_root / "public" / "runtimes" / "bundle.js").write_text(
        "console.log('bundle');\n",
        encoding="utf-8",
    )
    return repo_root


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
    assert [item.target.action_id for item in change_set.build_targets] == ["action:npm:build:@monorepo/core"]
    assert change_set.runner_actions == tuple()
    assert len(change_set.quality_validation_operations) == 1
    assert len(change_set.quality_hygiene_operations) == 1
    assert change_set.quality_validation_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.quality_hygiene_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.tests[0].proof_edges[0].edge_kind == MinimumVerifiedEvidenceEdgeKind.TARGET_TEST_TARGET
    assert change_set.quality_validation_operations[0].proof_edges[0].edge_kind == (
        MinimumVerifiedEvidenceEdgeKind.TARGET_QUALITY_VALIDATION
    )
    assert not any(item.reason_code.value == "runner_not_directly_validation_relevant" for item in change_set.excluded_items)
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


def test_minimum_verified_change_set_routes_quality_to_owning_provider_in_mixed_repo(tmp_path: Path) -> None:
    repository = Workspace(_make_mixed_go_npm_repo(tmp_path / "mixed")).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="server/internal/db/repo.go")
    )

    assert [item.target.test_definition.id for item in change_set.tests] == [
        "test:go:example.com/mixed/server/internal/db"
    ]
    assert change_set.quality_validation_operations == tuple()
    assert change_set.quality_hygiene_operations == tuple()


def test_minimum_verified_change_set_uses_direct_dependent_tests_when_file_has_no_local_go_tests(go_repo_root) -> None:
    repository = Workspace(go_repo_root).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="pkg/util/util.go")
    )

    assert [item.target.test_definition.id for item in change_set.tests] == [
        "test:go:example.com/acme/go-demo/internal/service"
    ]
    assert change_set.tests[0].inclusion_reason == "direct dependent component test"
    assert any(
        item.reason_code.value == "no_narrower_direct_validation_surface_for_file_target"
        and item.item_kind.value == "validation_surface"
        and "dependent-package surfaces required because the file is shared" in item.reason
        for item in change_set.excluded_items
    )
    assert change_set.build_targets == tuple()
    assert change_set.provenance


def test_minimum_verified_change_set_uses_direct_dependent_build_when_no_tests_exist(tmp_path: Path) -> None:
    repo_root = tmp_path / "go-no-tests"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/mvcsbuild\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "internal" / "lib").mkdir(parents=True)
    (repo_root / "internal" / "lib" / "lib.go").write_text(
        'package lib\n\nfunc Message() string { return "ok" }\n',
        encoding="utf-8",
    )
    (repo_root / "cmd" / "app").mkdir(parents=True)
    (repo_root / "cmd" / "app" / "main.go").write_text(
        'package main\n\nimport (\n    "fmt"\n    "example.com/mvcsbuild/internal/lib"\n)\n\nfunc main() { fmt.Println(lib.Message()) }\n',
        encoding="utf-8",
    )

    repository = Workspace(repo_root).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="internal/lib/lib.go")
    )

    assert change_set.tests == tuple()
    assert [item.target.action_id for item in change_set.build_targets] == [
        "action:go:build:example.com/mvcsbuild/cmd/app"
    ]
    assert change_set.build_targets[0].inclusion_reason == (
        "directly dependent buildable component is the narrowest deterministic build surface"
    )
    assert any(
        item.reason_code.value == "no_narrower_direct_validation_surface_for_file_target"
        and item.item_kind.value == "validation_surface"
        for item in change_set.excluded_items
    )
    assert change_set.provenance


def test_minimum_verified_change_set_prefers_direct_build_over_dependent_tests(npm_repo_root, monkeypatch) -> None:
    repository = Workspace(npm_repo_root).repositories[0]
    service = repository._build_minimum_verified_change_set_service()  # type: ignore[attr-defined]

    dependent_component = next(
        component
        for component in repository.arch.get_components()
        if component.id == "component:npm:@monorepo/utils"
    )
    dependency_edges = tuple(
        edge
        for edge in repository.arch.get_component_dependency_edges("component:npm:@monorepo/utils")
        if edge.target_id == "component:npm:@monorepo/core"
    )

    monkeypatch.setattr(service._candidate_resolver, "related_tests", lambda resolved: tuple())
    monkeypatch.setattr(
        service._candidate_resolver,
        "direct_dependent_components",
        lambda resolved: (
            type(
                "_ResolvedDependentComponent",
                (),
                {"component": dependent_component, "dependency_edges": dependency_edges},
            )(),
        ),
    )
    monkeypatch.setattr(
        service._candidate_resolver,
        "related_tests_for_dependent_components",
        lambda dependents: (
            (
                ResolvedRelatedTest(
                    match=RelatedTestMatch(
                        test_definition=repository.describe_test_target("test:npm:@monorepo/utils").test_definition,
                        relation_reason="dependent_component",
                        matched_owner_id="component:npm:@monorepo/utils",
                    ),
                    discovered_test=DiscoveredTestDefinition(
                        test_definition=repository.describe_test_target("test:npm:@monorepo/utils").test_definition,
                        provenance=repository.describe_test_target("test:npm:@monorepo/utils").provenance,
                    ),
                ),
                dependency_edges[0].provenance,
            ),
        ),
    )

    change_set = service.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="packages/core/src/index.ts")
    )

    assert change_set.tests == tuple()
    assert [item.target.action_id for item in change_set.build_targets] == ["action:npm:build:@monorepo/core"]
    assert any(
        item.reason_code.value == "dependent_test_replaced_by_narrower_build"
        and item.item_id == "test:npm:@monorepo/utils"
        for item in change_set.excluded_items
    )


def test_minimum_verified_change_set_reports_build_only_frontend_validation(tmp_path: Path) -> None:
    repository = Workspace(_make_frontend_build_only_repo(tmp_path / "frontend")).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="src/App.tsx")
    )

    assert change_set.tests == tuple()
    assert [item.target.action_id for item in change_set.build_targets] == ["action:npm:build:frontend"]
    assert tuple(facet.value for facet in change_set.build_targets[0].target.proof_facets) == (
        "typescript_typecheck",
        "frontend_bundle_build",
    )
    assert any(
        item.reason_code.value == "no_deterministic_test_targets_available"
        and "no finer deterministic frontend test target was discovered" in item.reason
        and "build is the primary deterministic frontend validation surface currently available" in item.reason
        for item in change_set.excluded_items
    )


def test_minimum_verified_change_set_does_not_inherit_source_validation_for_artifact_member(tmp_path: Path) -> None:
    repository = Workspace(_make_frontend_artifact_repo(tmp_path / "frontend-artifact")).repositories[0]

    change_set = repository.get_minimum_verified_change_set(
        ChangeTarget(repository_rel_path="public/runtimes/bundle.js")
    )

    assert change_set.tests == tuple()
    assert change_set.build_targets == tuple()
    assert change_set.quality_validation_operations == tuple()
    assert any(
        item.reason_code.value == "no_deterministic_validation_surface_for_artifact_member"
        and "public/runtimes" in item.reason
        for item in change_set.excluded_items
    )


def test_minimum_verified_change_set_fails_cleanly_when_no_surfaces_exist(tmp_path: Path) -> None:
    repo_root = tmp_path / "go-orphan"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/orphan\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "pkg" / "orphan").mkdir(parents=True)
    (repo_root / "pkg" / "orphan" / "orphan.go").write_text(
        'package orphan\n\nfunc Value() string { return "orphan" }\n',
        encoding="utf-8",
    )

    repository = Workspace(repo_root).repositories[0]

    with pytest.raises(
        ValueError,
        match=r"no deterministic validation surfaces were found for file target `pkg/orphan/orphan\.go`",
    ):
        repository.get_minimum_verified_change_set(ChangeTarget(repository_rel_path="pkg/orphan/orphan.go"))


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
