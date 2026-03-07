from __future__ import annotations

from pathlib import Path

import pytest
from suitcode.core.build_service import BuildService
from suitcode.core.runner_service import RunnerService
from suitcode.mcp.errors import McpNotFoundError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.providers.shared.action_execution import ActionExecutionResult, ActionExecutionStatus


def test_service_open_workspace_and_list_repositories(service: SuitMcpService, npm_repo_root: Path) -> None:
    opened = service.open_workspace(str(npm_repo_root))
    repositories = service.list_workspace_repositories(opened.workspace.workspace_id)

    assert opened.reused is False
    assert opened.workspace.repository_count == 1
    assert repositories.total == 1


def test_service_open_workspace_reuses_same_root(service: SuitMcpService, npm_repo_root: Path) -> None:
    first = service.open_workspace(str(npm_repo_root))
    second = service.open_workspace(str(npm_repo_root))

    assert first.workspace.workspace_id == second.workspace.workspace_id
    assert second.reused is True


def test_service_inspect_repository_support_for_unsupported_repo(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    support = service.inspect_repository_support(str(repo_root))

    assert support.is_supported is False


def test_service_open_workspace_fails_for_unsupported_repo(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    with pytest.raises(McpUnsupportedRepositoryError):
        service.open_workspace(str(repo_root))


def test_service_list_components_and_tests(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    components = service.list_components(workspace_id, repository_id, limit=10, offset=0)
    tests = service.list_tests(workspace_id, repository_id, limit=10, offset=0)

    assert components.total >= 1
    assert components.items[0].provenance
    assert tests.total >= 1
    assert hasattr(tests.items[0], "provenance")
    assert tests.items[0].provenance


def test_service_list_actions_and_filters(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    all_actions = service.list_actions(workspace_id, repository_id, limit=200, offset=0)
    assert all_actions.total >= 1
    assert all(item.provenance for item in all_actions.items)
    assert any(item.kind == "runner_execution" for item in all_actions.items)
    assert any(item.kind == "test_execution" for item in all_actions.items)

    runner_target = next(item.target_id for item in all_actions.items if item.target_kind == "runner")
    runner_actions = service.list_actions(
        workspace_id,
        repository_id,
        runner_id=runner_target,
        limit=200,
        offset=0,
    )
    assert runner_actions.total >= 1
    assert all(item.target_id == runner_target for item in runner_actions.items)

    test_actions = service.list_actions(
        workspace_id,
        repository_id,
        action_kinds=("test_execution",),
        limit=200,
        offset=0,
    )
    assert test_actions.total >= 1
    assert all(item.kind == "test_execution" for item in test_actions.items)


def test_service_lists_and_executes_build_targets(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)

    targets = service.list_build_targets(workspace_id, repository_id, limit=200, offset=0)
    assert targets.total >= 1
    assert targets.items[0].provenance
    action_id = targets.items[0].action_id

    described = service.describe_build_target(workspace_id, repository_id, action_id=action_id)
    assert described.action_id == action_id
    assert described.provenance

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

    target_result = service.build_target(
        workspace_id,
        repository_id,
        action_id=action_id,
        timeout_seconds=33,
    )
    assert target_result.action_id == action_id
    assert target_result.status == "passed"
    assert target_result.duration_ms == 33
    assert target_result.provenance

    project_result = service.build_project(
        workspace_id,
        repository_id,
        timeout_seconds=33,
    )
    assert project_result.total == targets.total
    assert project_result.passed == targets.total
    assert project_result.failed == 0
    assert project_result.errors == 0
    assert project_result.timeouts == 0
    assert project_result.failed_results == tuple()
    assert project_result.provenance


def test_service_build_methods_fail_fast_for_unknown_action(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_build_target(workspace_id, repository_id, action_id="action:missing")

    with pytest.raises(McpValidationError):
        service.build_target(workspace_id, repository_id, action_id="action:missing")


def test_service_list_actions_validates_query(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.list_actions(
            workspace_id,
            repository_id,
            owner_id="component:npm:@monorepo/core",
            component_id="component:npm:@monorepo/core",
        )

    with pytest.raises(McpValidationError):
        service.list_actions(
            workspace_id,
            repository_id,
            action_kinds=("unsupported",),
        )


def test_service_find_symbols_requires_valid_query(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.find_symbols(workspace_id, repository_id, query="   ")


def test_service_find_symbols_passes_case_sensitive_flag(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False):
            if is_case_sensitive and query == "core":
                return tuple()
            return (
                type("FakeSymbol", (), {
                    "name": "Core",
                    "kind": "class",
                    "repository_rel_path": "packages/core/src/index.ts",
                    "line_start": 1,
                    "line_end": 11,
                    "column_start": 1,
                    "column_end": 2,
                    "container_name": None,
                    "signature": None,
                })(),
            )

    provider._symbol_service = _FakeSymbolService()  # type: ignore[attr-defined]

    insensitive = service.find_symbols(workspace_id, repository_id, query="core", limit=50, offset=0)
    sensitive = service.find_symbols(
        workspace_id,
        repository_id,
        query="core",
        is_case_sensitive=True,
        limit=50,
        offset=0,
    )

    assert insensitive.total >= 1
    assert insensitive.items[0].provenance
    assert sensitive.total == 0


def test_service_quality_requires_provider_id(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.format_file(workspace_id, repository_id, "packages/core/src/index.ts", provider_id="missing")


def test_service_quality_results_include_provenance(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool):
            from suitcode.core.provenance_builders import lsp_delta_provenance, quality_tool_provenance
            from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult

            return QualityFileResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=False,
                success=True,
                message=None,
                diagnostics=(
                    QualityDiagnostic(
                        tool="eslint",
                        severity="warning",
                        message="issue",
                        provenance=(
                            quality_tool_provenance(
                                source_tool="eslint",
                                evidence_summary="eslint diagnostic",
                                evidence_paths=(repository_rel_path,),
                            ),
                        ),
                    ),
                ),
                entity_delta=QualityEntityDelta(
                    provenance=(
                        lsp_delta_provenance(
                            source_tool="typescript-language-server",
                            evidence_summary="delta from lsp",
                            evidence_paths=(repository_rel_path,),
                        ),
                    ),
                ),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="before",
                provenance=(
                    quality_tool_provenance(
                        source_tool="eslint",
                        evidence_summary="eslint result",
                        evidence_paths=(repository_rel_path,),
                    ),
                    lsp_delta_provenance(
                        source_tool="typescript-language-server",
                        evidence_summary="result includes lsp delta",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            )

    provider._quality_service = _FakeQualityService()  # type: ignore[attr-defined]

    result = service.lint_file(
        workspace_id,
        repository_id,
        "packages/core/src/index.ts",
        provider_id="npm",
        is_fix=False,
    )

    assert result.provenance
    assert result.diagnostics[0].provenance
    assert result.entity_delta.provenance


def test_service_close_workspace_invalidates_lookup(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id

    service.close_workspace(workspace_id)

    with pytest.raises(McpNotFoundError):
        service.get_workspace(workspace_id)


def test_service_pagination_enforces_limit(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.list_components(workspace_id, repository_id, limit=201, offset=0)


def test_service_exposes_owner_related_test_and_summary_tools(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    file_owner = service.get_file_owner(workspace_id, repository_id, "packages/core/src/index.ts")
    owned_files = service.list_files_by_owner(
        workspace_id,
        repository_id,
        owner_id="component:npm:@monorepo/core",
        limit=50,
        offset=0,
    )
    related_tests = service.get_related_tests(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    summary = service.repository_summary(workspace_id, repository_id, preview_limit=5)

    assert file_owner.owner.id == "component:npm:@monorepo/core"
    assert owned_files.total >= 1
    assert any(item.id == "test:npm:@monorepo/core" for item in related_tests.items)
    assert all(item.provenance for item in related_tests.items)
    assert summary.repository_id == repository_id
    assert summary.preview_limit == 5
    assert summary.component_count >= 1
    assert summary.provenance
    assert any(item.source_kind == "test_tool" for item in summary.provenance)


def test_service_describe_and_run_test_targets(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    description = service.describe_test_target(
        workspace_id,
        repository_id,
        test_id="test:npm:@monorepo/core",
    )
    assert description.id == "test:npm:@monorepo/core"
    assert description.command_argv
    assert description.provenance

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
                        evidence_paths=("packages/core/src/index.test.ts",),
                    ),
                ),
            )

    provider._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
    run_result = service.run_test_targets(
        workspace_id,
        repository_id,
        test_ids=("test:npm:@monorepo/core",),
        timeout_seconds=25,
    )

    assert run_result.total == 1
    assert run_result.passed == 1
    assert run_result.results[0].test_id == "test:npm:@monorepo/core"
    assert run_result.results[0].duration_ms == 25


def test_service_describe_and_run_runner(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)

    runners = service.list_runners(workspace_id, repository_id, limit=10, offset=0)
    assert runners.total >= 1
    runner_id = runners.items[0].id

    context = service.describe_runner(workspace_id, repository_id, runner_id=runner_id)
    assert context.runner.id == runner_id
    assert context.action_id
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
    run_result = service.run_runner(
        workspace_id,
        repository_id,
        runner_id=runner_id,
        timeout_seconds=21,
    )

    assert run_result.runner_id == runner_id
    assert run_result.status == "passed"
    assert run_result.duration_ms == 21


def test_service_runner_methods_fail_fast_for_unknown_runner(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_runner(workspace_id, repository_id, runner_id="runner:missing")

    with pytest.raises(McpValidationError):
        service.run_runner(workspace_id, repository_id, runner_id="runner:missing")


def test_service_exposes_component_file_and_impact_context(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return (
                type(
                    "FakeSymbol",
                    (),
                    {
                        "name": "Core",
                        "kind": "class",
                        "repository_rel_path": "packages/core/src/index.ts",
                        "line_start": 1,
                        "line_end": 13,
                        "column_start": 1,
                        "column_end": 2,
                        "container_name": None,
                        "signature": "class Core",
                    },
                )(),
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (
                ("packages/core/src/index.ts", 1, 13, 1, 2),
                ("packages/utils/src/index.ts", 7, 9, 1, 2),
            )

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]

    component_contexts = service.describe_components(
        workspace_id,
        repository_id,
        component_ids=("component:npm:@monorepo/core",),
    )
    file_contexts = service.describe_files(
        workspace_id,
        repository_id,
        repository_rel_paths=("packages/core/src/index.ts",),
    )
    symbol_context = service.describe_symbol_context(
        workspace_id,
        repository_id,
        symbol_id="entity:packages/core/src/index.ts:class:Core:1-13",
    )
    dependencies = service.get_component_dependencies(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/utils",
        limit=50,
        offset=0,
    )
    dependency_edges = service.list_component_dependency_edges(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/utils",
        limit=50,
        offset=0,
    )
    dependents = service.get_component_dependents(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/core",
        limit=50,
        offset=0,
    )
    impact = service.analyze_impact(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )
    change = service.analyze_change(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert component_contexts[0].component.id == "component:npm:@monorepo/core"
    assert component_contexts[0].component.provenance
    assert file_contexts[0].owner.id == "component:npm:@monorepo/core"
    assert file_contexts[0].file.provenance
    assert symbol_context.symbol.name == "Core"
    assert symbol_context.symbol.provenance
    assert symbol_context.definitions[0].provenance
    assert impact.references_preview[0].provenance
    assert any(item.target_id == "component:npm:@monorepo/core" for item in dependencies.items)
    assert all(item.source_component_id == "component:npm:@monorepo/utils" for item in dependency_edges.items)
    assert {item.target_id for item in dependency_edges.items} == {item.target_id for item in dependencies.items}
    assert "component:npm:@monorepo/utils" in dependents.items
    assert impact.target_kind == "file"
    assert change.target_kind == "file"
    assert change.primary_component is not None
    assert change.primary_component.id == "component:npm:@monorepo/core"
    assert change.reference_locations
    assert change.related_tests
    assert isinstance(change.related_runners, tuple)
    if change.related_runners:
        assert change.related_runners[0].provenance
    assert change.quality_gates
    assert change.provenance


def test_service_list_component_dependency_edges_fails_for_unknown_component(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpNotFoundError):
        service.list_component_dependency_edges(
            workspace_id,
            repository_id,
            component_id="component:npm:missing",
        )


def test_service_exact_batch_and_preview_validation_fail_fast(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_components(
            workspace_id,
            repository_id,
            component_ids=("component:npm:@monorepo/core", "component:npm:@monorepo/core"),
        )

    with pytest.raises(McpValidationError):
        service.describe_files(
            workspace_id,
            repository_id,
            repository_rel_paths=tuple(),
        )

    with pytest.raises(McpValidationError):
        service.analyze_change(
            workspace_id,
            repository_id,
            symbol_id="entity:packages/core/src/index.ts:class:Core:1-13",
            repository_rel_path="packages/core/src/index.ts",
        )

    with pytest.raises(McpValidationError):
        service.analyze_change(
            workspace_id,
            repository_id,
            repository_rel_path="packages/core/src/index.ts",
            runner_preview_limit=0,
        )


def test_service_analytics_views_return_structured_data(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository_root = service._registry.get_repository(workspace_id, repository_id).root

    service.analytics_recorder.record_success(
        tool_name="list_supported_providers",
        arguments={},
        repository_root=None,
        result={"items": [{"provider_id": "python"}]},
        duration_ms=7,
    )
    service.analytics_recorder.record_success(
        tool_name="list_components",
        arguments={"workspace_id": workspace_id, "repository_id": repository_id, "limit": 10, "offset": 0},
        repository_root=repository_root,
        result={"items": [{"id": "component:npm:@monorepo/core"}]},
        duration_ms=9,
    )

    summary_repo_local = service.get_analytics_summary(
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
    summary_with_global = service.get_analytics_summary(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
    )
    session_id = service.analytics_recorder._session_id  # type: ignore[attr-defined]
    usage = service.get_tool_usage_analytics(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
        session_id=session_id,
        limit=50,
        offset=0,
    )
    ineff = service.get_inefficient_tool_calls(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
        session_id=session_id,
        limit=50,
        offset=0,
    )

    assert summary_repo_local.total_calls >= 1
    assert summary_with_global.total_calls >= summary_repo_local.total_calls
    assert summary_repo_local.estimated_tokens >= 1
    assert usage.total >= 1
    assert isinstance(ineff.items, tuple)
    if ineff.items:
        assert ineff.items[0].session_id == session_id


def test_service_benchmark_report_fails_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUITCODE_ANALYTICS_GLOBAL_ROOT", str(tmp_path / "analytics"))
    service = SuitMcpService(registry=WorkspaceRegistry())
    with pytest.raises(McpNotFoundError):
        service.get_mcp_benchmark_report()
