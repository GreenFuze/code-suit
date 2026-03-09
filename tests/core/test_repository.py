from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from suitcode.core.build_service import BuildService
from suitcode.core.repository import Repository
from suitcode.core.runner_service import RunnerService
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.shared.action_execution import ActionExecutionResult, ActionExecutionStatus


def _make_supported_npm_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "packages" / "app").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{"name":"repo","private":true,"workspaces":["packages/*"]}\n',
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "package.json").write_text(
        '{"name":"@repo/app","version":"1.0.0","scripts":{"test":"jest"}}\n',
        encoding="utf-8",
    )
    return repo_root


def _make_supported_npm_repo_with_runner(repo_root: Path) -> Path:
    _make_supported_npm_repo(repo_root)
    (repo_root / "packages" / "app" / "package.json").write_text(
        '{"name":"@repo/app","version":"1.0.0","scripts":{"build":"node build.js","test":"jest"}}\n',
        encoding="utf-8",
    )
    return repo_root


def test_repository_creates_suit_layout_and_back_reference() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = _make_supported_npm_repo(Path(td) / "repo")

        workspace = Workspace(repo_root)
        repository = workspace.repositories[0]

        assert repository.workspace is workspace
        assert repository.root == repo_root
        assert repository.suit_dir == repo_root / ".suit"
        assert (repository.suit_dir / "config.json").exists()
        assert (repository.suit_dir / "state.json").exists()


def test_repository_detects_registered_providers_and_intelligence() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo(Path(td) / "repo")).repositories[0]

        assert repository.provider_ids == ("npm",)
        assert repository.provider_roles["npm"] == frozenset(
            {
                ProviderRole.ARCHITECTURE,
                ProviderRole.CODE,
                ProviderRole.TEST,
                ProviderRole.QUALITY,
            }
        )
        assert repository.arch.repository is repository
        assert repository.code.repository is repository
        assert repository.tests.repository is repository
        assert repository.quality.repository is repository
        assert repository.actions.repository is repository


def test_repository_root_candidate_prefers_nearest_supported_root_over_vcs_root() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        nested_repo = repo_root / "nested"
        (repo_root / ".git").mkdir(parents=True)
        nested_repo.mkdir(parents=True)
        (nested_repo / "package.json").write_text(
            '{"name":"nested","private":true,"workspaces":["packages/*"]}\n',
            encoding="utf-8",
        )
        package_dir = nested_repo / "packages" / "app"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"name":"@nested/app","version":"1.0.0","scripts":{"test":"jest"}}\n',
            encoding="utf-8",
        )

        assert Repository.root_candidate(nested_repo) == nested_repo


def test_repository_root_candidate_falls_back_to_vcs_root_when_no_supported_nested_root_exists() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        nested = repo_root / "src" / "pkg"
        (repo_root / ".git").mkdir(parents=True)
        nested.mkdir(parents=True)

        assert Repository.root_candidate(nested) == repo_root


def test_repository_ids_are_collision_safe_with_same_basename() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo_one = _make_supported_npm_repo(base / "one" / "app")
        repo_two = _make_supported_npm_repo(base / "two" / "app")

        workspace = Workspace(repo_one)
        first = workspace.repositories[0]
        second = workspace.add_repository(repo_two)

        assert first.id == "repo:app"
        assert second.id == "repo:app-2"


def test_repository_support_for_path_reports_unsupported_repository() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        support = Repository.support_for_path(repo_root)

        assert support.repository_root == repo_root
        assert support.is_supported is False
        assert support.provider_ids == tuple()


def test_repository_construction_fails_when_no_provider_matches() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)
        workspace_root = Path(td) / "workspace"
        workspace_root.mkdir(parents=True)
        (workspace_root / "package.json").write_text('{"name":"ws","private":true,"workspaces":["packages/*"]}\n', encoding="utf-8")
        (workspace_root / ".git").mkdir(parents=True)

        workspace = Workspace(workspace_root)

        try:
            workspace.add_repository(repo_root)
        except ValueError as exc:
            assert "unsupported repository" in str(exc)
        else:
            raise AssertionError("expected unsupported repository to fail")


def test_repository_list_files_by_owner_and_batch_validation_fail_fast() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo(Path(td) / "repo")).repositories[0]

        files = repository.list_files_by_owner("component:npm:@repo/app")
        assert any(item.repository_rel_path == "packages/app/package.json" for item in files)

        try:
            repository.describe_components(("component:npm:@repo/app", "component:npm:@repo/app"))
        except ValueError as exc:
            assert "duplicates" in str(exc)
        else:
            raise AssertionError("expected duplicate component batch to fail")

        try:
            repository.describe_files(tuple())
        except ValueError as exc:
            assert "must not be empty" in str(exc)
        else:
            raise AssertionError("expected empty file batch to fail")


def test_repository_exposes_test_target_description_and_run_methods() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo(Path(td) / "repo")).repositories[0]
        description = repository.describe_test_target("test:npm:@repo/app")
        assert description.test_definition.id == "test:npm:@repo/app"
        assert description.command_argv

        class _FakeExecutionService:
            def run_target(self, target_description, timeout_seconds: int):
                from suitcode.core.provenance_builders import heuristic_provenance
                from suitcode.core.tests.models import TestExecutionResult, TestExecutionStatus

                return TestExecutionResult(
                    test_id=target_description.test_definition.id,
                    status=TestExecutionStatus.PASSED,
                    success=True,
                    command_argv=target_description.command_argv,
                    command_cwd=target_description.command_cwd,
                    exit_code=0,
                    duration_ms=timeout_seconds,
                    log_path=".suit/runs/tests/fake.log",
                    warning=target_description.warning,
                    output_excerpt="ok",
                    provenance=(
                        heuristic_provenance(
                            evidence_summary="fake execution result",
                            evidence_paths=("packages/app/package.json",),
                        ),
                    ),
                )

        repository.get_provider("npm")._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
        result = repository.run_test_targets(("test:npm:@repo/app",), timeout_seconds=15)
        assert result[0].test_id == "test:npm:@repo/app"
        assert result[0].duration_ms == 15


def test_repository_exposes_runner_context_and_run_methods() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo_with_runner(Path(td) / "repo")).repositories[0]
        runner_id = repository.arch.get_runners()[0].id

        context = repository.describe_runner(runner_id, file_preview_limit=10, test_preview_limit=10)
        assert context.runner.id == runner_id
        assert context.action_id.startswith("action:npm:runner:")
        assert context.provenance

        class _FakeActionExecutionService:
            def run(
                self,
                *,
                action_id: str,
                command_argv: tuple[str, ...],
                command_cwd: str | None,
                timeout_seconds: int,
                run_group: str,
            ) -> ActionExecutionResult:
                return ActionExecutionResult(
                    action_id=action_id,
                    status=ActionExecutionStatus.PASSED,
                    success=True,
                    command_argv=command_argv,
                    command_cwd=command_cwd,
                    exit_code=0,
                    duration_ms=timeout_seconds,
                    log_path=".suit/runs/runners/fake.log",
                    output_excerpt="ok",
                    output="ok",
                )

        repository._runner_service = RunnerService(  # type: ignore[attr-defined]
            repository,
            action_execution_service=_FakeActionExecutionService(),
        )
        result = repository.run_runner(runner_id, timeout_seconds=12)

        assert result.runner_id == runner_id
        assert result.status.value == "passed"
        assert result.duration_ms == 12


def test_repository_exposes_build_target_and_project_methods() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo_with_runner(Path(td) / "repo")).repositories[0]
        targets = repository.list_build_targets()
        assert len(targets) == 1
        target = targets[0]
        assert target.provenance

        described = repository.describe_build_target(target.action_id)
        assert described.action_id == target.action_id

        class _FakeActionExecutionService:
            def run(
                self,
                *,
                action_id: str,
                command_argv: tuple[str, ...],
                command_cwd: str | None,
                timeout_seconds: int,
                run_group: str,
            ) -> ActionExecutionResult:
                return ActionExecutionResult(
                    action_id=action_id,
                    status=ActionExecutionStatus.PASSED,
                    success=True,
                    command_argv=command_argv,
                    command_cwd=command_cwd,
                    exit_code=0,
                    duration_ms=timeout_seconds,
                    log_path=".suit/runs/builds/fake.log",
                    output_excerpt="ok",
                    output="ok",
                )

        repository._build_service = BuildService(  # type: ignore[attr-defined]
            repository,
            action_execution_service=_FakeActionExecutionService(),
        )
        single_result = repository.build_target(target.action_id, timeout_seconds=18)
        assert single_result.action_id == target.action_id
        assert single_result.status.value == "passed"
        assert single_result.duration_ms == 18
        assert single_result.provenance

        project_result = repository.build_project(timeout_seconds=18)
        assert project_result.total == 1
        assert project_result.passed == 1
        assert project_result.failed == 0
        assert project_result.failed_results == tuple()
        assert project_result.succeeded_target_ids == (target.target_id,)
        assert project_result.provenance


def test_repository_build_project_fails_fast_without_build_targets() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo(Path(td) / "repo")).repositories[0]
        assert repository.list_build_targets() == tuple()
        with pytest.raises(ValueError, match="no deterministic build targets"):
            repository.build_project()
