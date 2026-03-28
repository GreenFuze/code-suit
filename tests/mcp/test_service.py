from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from suitcode.core.build_service import BuildService
from suitcode.core.intelligence_models import FileRelationshipKind, FileRelationshipRef
from suitcode.core.provenance_builders import dependency_graph_provenance
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
    assert opened.initial_repository.root_path == str(npm_repo_root)
    assert opened.initial_repository.provider_ids == ("go", "npm", "python")
    assert opened.initial_repository.provider_attachment_roots["npm"] == (".",)
    assert opened.initial_repository.provider_attachment_roots["python"] == ("tools/codegen",)
    assert opened.guidance.session_scope == "process_local"
    assert "process" in opened.guidance.message.lower()
    assert "repository_summary" in opened.guidance.recommended_next_calls
    assert "repository_summary_by_path" in opened.guidance.read_only_alternatives
    assert repositories.total == 1


def test_service_core_tools_reuse_existing_repository_intelligence(service: SuitMcpService, npm_repo_root: Path) -> None:
    understanding = service.understand_repository(str(npm_repo_root), preview_limit=5)
    file_understanding = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
    )
    impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )
    minimum = service.what_should_i_run(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )
    availability = service.can_i_do_this(
        str(npm_repo_root),
        "packages/core/src/index.ts",
        "test",
    )

    assert understanding.repository.component_count >= 1
    assert understanding.truth_coverage.domains
    assert understanding.provenance
    assert file_understanding.target_count == 1
    assert file_understanding.targets[0].file_owner.owner.id == "component:npm:@monorepo/core"
    assert file_understanding.aggregate_related_tests
    assert file_understanding.provenance
    assert impact.target_count == 1
    assert impact.targets[0].impact.target_kind == "file"
    assert impact.provenance
    assert minimum.target_count == 1
    assert minimum.compact_summary.required_validation_count >= 1
    assert minimum.targets[0].change_set.owner.id == "component:npm:@monorepo/core"
    assert availability.supported is True
    assert "test" in availability.available_action_kinds
    assert availability.provenance


def test_read_only_by_path_tools_match_workspace_tools_without_registry_mutation(service: SuitMcpService, npm_repo_root: Path) -> None:
    shutil.rmtree(npm_repo_root / ".suit", ignore_errors=True)
    assert not (npm_repo_root / ".suit").exists()
    assert service.list_open_workspaces().total == 0

    summary_by_path = service.repository_summary_by_path(str(npm_repo_root), preview_limit=5)
    owner_by_path = service.get_file_owner_by_path(str(npm_repo_root), "packages/core/src/index.ts")
    related_by_path = service.get_related_tests_by_path(
        str(npm_repo_root),
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    change_set_by_path = service.get_minimum_verified_change_set_by_path(
        str(npm_repo_root),
        repository_rel_path="packages/core/src/index.ts",
    )

    assert service.list_open_workspaces().total == 0
    assert not (npm_repo_root / ".suit").exists()

    opened = service.open_workspace(str(npm_repo_root))
    workspace_id = opened.workspace.workspace_id
    repository_id = opened.initial_repository.repository_id

    summary = service.repository_summary(workspace_id, repository_id, preview_limit=5)
    owner = service.get_file_owner(workspace_id, repository_id, "packages/core/src/index.ts")
    related = service.get_related_tests(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    change_set = service.get_minimum_verified_change_set(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert summary_by_path.model_dump() == summary.model_dump()
    assert owner_by_path.model_dump() == owner.model_dump()
    assert related_by_path.model_dump() == related.model_dump()
    assert change_set_by_path.model_dump() == change_set.model_dump()


def test_read_only_by_path_tools_validate_and_map_errors(service: SuitMcpService, npm_repo_root: Path, tmp_path: Path) -> None:
    with pytest.raises(McpValidationError):
        service.repository_summary_by_path(str(npm_repo_root), preview_limit=0)

    with pytest.raises(McpValidationError):
        service.get_related_tests_by_path(str(npm_repo_root))

    with pytest.raises(McpValidationError):
        service.get_minimum_verified_change_set_by_path(str(npm_repo_root))

    with pytest.raises(McpNotFoundError):
        service.get_file_owner_by_path(str(npm_repo_root), "missing/file.ts")

    unsupported_root = tmp_path / "repo"
    unsupported_root.mkdir()
    (unsupported_root / ".git").mkdir()

    with pytest.raises(McpUnsupportedRepositoryError):
        service.repository_summary_by_path(str(unsupported_root))


def test_understand_file_supports_standalone_npm_package_root(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
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
    (repo_root / "src" / "pages" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")

    understanding = service.understand_file(
        str(repo_root),
        ("src/pages/LibraryPage.tsx",),
        related_test_limit=5,
    )

    assert understanding.targets[0].file_owner.owner.id == "component:npm:frontend"


def test_understand_file_supports_standalone_npm_public_runtime_asset(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "public" / "runtimes" / "demo").mkdir(parents=True)
    (repo_root / "package.json").write_text(
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
    (repo_root / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    (repo_root / "public" / "runtimes" / "demo" / "runtime.js").write_text("console.log('runtime');\n", encoding="utf-8")

    understanding = service.understand_file(
        str(repo_root),
        ("public/runtimes/demo/runtime.js",),
        related_test_limit=5,
    )

    assert understanding.targets[0].file_owner.owner.id == "component:npm:frontend"


def test_understand_repository_accepts_larger_preview_limit(service: SuitMcpService, npm_repo_root: Path) -> None:
    understanding = service.understand_repository(str(npm_repo_root), preview_limit=50)

    assert understanding.repository.preview_limit == 50


def test_understand_file_reports_unowned_artifacts_clearly(service: SuitMcpService, npm_repo_root: Path) -> None:
    (npm_repo_root / "notes.txt").write_text("plain text\n", encoding="utf-8")

    with pytest.raises(McpValidationError, match="provider-owned files"):
        service.understand_file(
            str(npm_repo_root),
            ("notes.txt",),
        )


def test_understand_file_returns_markdown_structure(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "docs-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "roadmap.md").write_text(
        "---\n"
        "title: Roadmap\n"
        "owner: docs\n"
        "---\n\n"
        "# Plan\n\n"
        "See [tracking](docs/tracking.md).\n\n"
        "- [x] discovery\n"
        "- [ ] rollout\n\n"
        "## Commands\n\n"
        "```bash\n"
        "npm run build\n"
        "```\n",
        encoding="utf-8",
    )

    understanding = service.understand_file(
        str(repo_root),
        ("roadmap.md",),
        related_test_limit=5,
    )

    target = understanding.targets[0]
    assert target.file_owner.owner.id == "component:markdown:documents"
    assert target.structured_artifact is not None
    assert target.structured_artifact.artifact_kind == "markdown_document"
    assert target.structured_artifact.markdown is not None
    assert target.structured_artifact.markdown.section_count == 2
    assert target.structured_artifact.markdown.sections[0].heading == "Plan"
    assert target.structured_artifact.markdown.sections[0].line_start == 6
    assert target.structured_artifact.markdown.sections[1].heading == "Commands"
    assert target.structured_artifact.markdown.code_block_count == 1
    assert target.structured_artifact.markdown.links[0].destination == "docs/tracking.md"
    assert target.structured_artifact.markdown.frontmatter is not None
    assert target.structured_artifact.markdown.frontmatter.keys == ("title", "owner")
    assert target.structured_artifact.markdown.checklist_item_count == 2
    assert understanding.suggested_follow_ups == tuple()


def test_frontend_standalone_package_surfaces_build_script_as_action(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build",
            "dev": "vite"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/pages/LibraryPage.tsx",),
    )
    availability = service.can_i_do_this(
        str(repo_root),
        repository_rel_path="src/pages/LibraryPage.tsx",
        requested_action_kind="build",
    )

    assert [item.action_id for item in minimum.build_targets] == ["action:npm:build:frontend"]
    assert minimum.build_targets[0].invocation.argv_preview == ("npm", "run", "build")
    assert any(item.reason_code == "no_deterministic_test_targets_available" for item in minimum.excluded_items)
    assert availability.supported is True
    assert "build" in availability.available_action_kinds


def test_frontend_standalone_package_uses_test_prefixed_script_for_validation(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "test:unit": "vitest run"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")
    (repo_root / "src" / "LibraryPage.spec.jsx").write_text("it('works', () => {});\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/LibraryPage.tsx",),
    )
    availability = service.can_i_do_this(
        str(repo_root),
        repository_rel_path="src/LibraryPage.tsx",
        requested_action_kind="test",
    )

    assert [item.test_id for item in minimum.tests] == ["test:npm:frontend"]
    assert minimum.tests[0].command.argv_preview == ("npm", "run", "test:unit")
    assert not any(item.reason_code == "no_deterministic_test_targets_available" for item in minimum.excluded_items)
    assert availability.supported is True
    assert "test" in availability.available_action_kinds


def test_frontend_standalone_package_prefers_non_watch_test_script(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "test:watch": "vitest --watch",
            "test:unit": "vitest run"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")
    (repo_root / "src" / "LibraryPage.spec.tsx").write_text("it('works', () => {});\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/LibraryPage.tsx",),
    )

    assert [item.test_id for item in minimum.tests] == ["test:npm:frontend"]
    assert minimum.tests[0].command.argv_preview == ("npm", "run", "test:unit")


def test_repository_summary_excludes_tracked_artifact_files_from_file_count(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "dist").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "main": "dist/index.js"
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    (repo_root / "dist" / "index.js").write_text("export const value = 1;\n", encoding="utf-8")

    understanding = service.understand_repository(str(repo_root), preview_limit=10)

    assert understanding.repository.file_count == 2
    ownership_provenance = next(
        item for item in understanding.repository.provenance if item.source_kind == "ownership"
    )
    assert "dist/index.js" not in ownership_provenance.evidence_paths


def test_read_only_by_path_minimum_verified_change_set_returns_clear_empty_surface_error(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "go-orphan"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/orphan\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "pkg" / "orphan").mkdir(parents=True)
    (repo_root / "pkg" / "orphan" / "orphan.go").write_text(
        'package orphan\n\nfunc Value() string { return "orphan" }\n',
        encoding="utf-8",
    )

    with pytest.raises(
        McpValidationError,
        match=r"no deterministic validation surfaces were found for file target `pkg/orphan/orphan\.go`",
    ):
        service.get_minimum_verified_change_set_by_path(
            str(repo_root),
            repository_rel_path="pkg/orphan/orphan.go",
        )


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
    assert summary.truth_coverage is None
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

    class _FakeRelationshipService:
        def get_file_relationships(self, repository_rel_path: str) -> tuple[FileRelationshipRef, ...]:
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                FileRelationshipRef(
                    repository_rel_path="packages/utils/src/index.ts",
                    relationship_kind=FileRelationshipKind.IMPORTED_BY,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved import edge",
                            evidence_paths=("packages/core/src/index.ts", "packages/utils/src/index.ts"),
                        ),
                    ),
                ),
            )

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]
    provider._file_relationship_service = _FakeRelationshipService()  # type: ignore[attr-defined]

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
    assert file_contexts[0].dependency_file_count == 0
    assert [item.path for item in file_contexts[0].dependent_files_preview] == ["packages/utils/src/index.ts"]
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
    assert [item.path for item in change.dependent_files] == ["packages/utils/src/index.ts"]
    assert change.reference_locations
    assert change.related_tests
    assert isinstance(change.related_runners, tuple)
    if change.related_runners:
        assert change.related_runners[0].provenance
    assert change.quality_gates
    assert change.evidence.total_edges >= 1
    assert change.evidence.counts_by_kind["target_owner"] == 1
    assert change.evidence.edges_preview[0].provenance
    assert change.truth_coverage.scope_kind == "change"
    assert change.provenance


def test_service_get_truth_coverage(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    truth = service.get_truth_coverage(workspace_id, repository_id)

    assert truth.scope_kind == "repository"
    assert truth.scope_id == repository_id
    assert {item.domain for item in truth.domains} == {
        "architecture",
        "code",
        "tests",
        "quality",
        "actions",
    }
    assert truth.provenance


def test_service_gets_minimum_verified_change_set(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    change_set = service.get_minimum_verified_change_set(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert change_set.compact_summary.required_validation_count >= 1
    assert change_set.compact_summary.required_validation[0].summary
    assert change_set.target_kind == "file"
    assert change_set.owner.id == "component:npm:@monorepo/core"
    assert [item.test_id for item in change_set.tests] == ["test:npm:@monorepo/core"]
    assert change_set.tests[0].command.total_arg_count >= 1
    assert change_set.quality_validation_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.quality_validation_operations[0].proof_edges[0].provenance
    assert change_set.provenance


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
