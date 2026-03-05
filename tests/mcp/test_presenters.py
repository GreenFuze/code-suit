from __future__ import annotations

from suitcode.core.change_models import ChangeImpact, QualityGateInfo, RunnerImpact, TestImpact as ChangeTestImpact
from suitcode.core.workspace import Workspace
from suitcode.core.models import EntityInfo
from suitcode.core.code.models import CodeLocation
from suitcode.core.provenance_builders import derived_summary_provenance, lsp_location_provenance, lsp_provenance, ownership_provenance
from suitcode.core.provenance_builders import lsp_delta_provenance, quality_tool_provenance
from suitcode.core.provenance import SourceKind
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.mcp.presenters import ArchitecturePresenter, ChangeImpactPresenter, CodePresenter, ProviderPresenter, QualityPresenter, RepositoryPresenter, TestPresenter as McpTestPresenter, WorkspacePresenter
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult
from suitcode.providers.npm import NPMProvider


def test_provider_presenter_maps_descriptor() -> None:
    descriptor = NPMProvider.descriptor()
    view = ProviderPresenter().descriptor_view(descriptor)

    assert view.provider_id == "npm"
    assert "architecture" in view.supported_roles


def test_workspace_and_repository_presenters_map_core_objects(npm_repo_root) -> None:
    workspace = Workspace(npm_repo_root)
    repository = workspace.repositories[0]
    workspace_view = WorkspacePresenter().workspace_view(workspace)
    repository_view = RepositoryPresenter().repository_view(repository)

    assert workspace_view.workspace_id.startswith("workspace:")
    assert repository_view.repository_id.startswith("repo:")
    assert repository_view.provider_ids == ("npm",)


def test_test_presenter_maps_provenance(npm_repo_root) -> None:
    workspace = Workspace(npm_repo_root)
    repository = workspace.repositories[0]
    discovered_test = repository.tests.get_discovered_tests()[0]

    view = McpTestPresenter().test_view(discovered_test)

    assert view.provenance
    assert view.provenance[0].evidence_summary


def test_test_presenter_maps_test_target_and_run_views(npm_repo_root) -> None:
    workspace = Workspace(npm_repo_root)
    repository = workspace.repositories[0]
    presenter = McpTestPresenter()
    description = repository.describe_test_target("test:npm:@monorepo/core")
    description_view = presenter.test_target_description_view(description)

    assert description_view.id == "test:npm:@monorepo/core"
    assert description_view.command_argv
    assert description_view.provenance

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

    repository.get_provider("npm")._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
    result = repository.run_test_targets(("test:npm:@monorepo/core",), timeout_seconds=10)
    run_view = presenter.run_test_targets_view(
        workspace_id=workspace.id,
        repository_id=repository.id,
        timeout_seconds=10,
        results=result,
    )

    assert run_view.total == 1
    assert run_view.passed == 1
    assert run_view.results[0].provenance


def test_architecture_and_code_presenters_map_raw_node_provenance(npm_repo_root) -> None:
    workspace = Workspace(npm_repo_root)
    repository = workspace.repositories[0]
    component = repository.arch.get_components()[0]
    symbol = EntityInfo(
        id="entity:packages/core/src/index.ts:class:Core:1-13",
        name="Core",
        repository_rel_path="packages/core/src/index.ts",
        entity_kind="class",
        line_start=1,
        line_end=13,
        provenance=(
            lsp_provenance(
                source_tool="typescript-language-server",
                evidence_summary="discovered from test LSP fixture",
                evidence_paths=("packages/core/src/index.ts",),
            ),
        ),
    )

    component_view = ArchitecturePresenter().component_view(component)
    symbol_view = CodePresenter().symbol_view(symbol)

    assert component_view.provenance
    assert symbol_view.provenance


def test_code_presenter_maps_location_provenance() -> None:
    view = CodePresenter().location_view(
        CodeLocation(
            repository_rel_path="packages/core/src/index.ts",
            line_start=1,
            line_end=13,
            column_start=1,
            column_end=2,
            provenance=(
                lsp_location_provenance(
                    source_tool="typescript-language-server",
                    repository_rel_path="packages/core/src/index.ts",
                    operation="definition",
                ),
            ),
        )
    )

    assert view.provenance
    assert view.provenance[0].source_kind == "lsp"


def test_quality_presenter_maps_quality_provenance() -> None:
    view = QualityPresenter().quality_file_result_view(
        workspace_id="workspace:x",
        repository_id="repo:x",
        provider_id="python",
        result=QualityFileResult(
            repository_rel_path="src/acme/core/repository.py",
            tool="ruff",
            operation="lint",
            changed=False,
            success=True,
            message=None,
            diagnostics=(
                QualityDiagnostic(
                    tool="ruff",
                    severity="warning",
                    message="issue",
                    provenance=(
                        quality_tool_provenance(
                            source_tool="ruff",
                            evidence_summary="ruff diagnostic",
                            evidence_paths=("src/acme/core/repository.py",),
                        ),
                    ),
                ),
            ),
            entity_delta=QualityEntityDelta(
                provenance=(
                    lsp_delta_provenance(
                        source_tool="basedpyright",
                        evidence_summary="delta from lsp",
                        evidence_paths=("src/acme/core/repository.py",),
                    ),
                ),
            ),
            applied_fixes=False,
            content_sha_before="before",
            content_sha_after="before",
            provenance=(
                quality_tool_provenance(
                    source_tool="ruff",
                    evidence_summary="ruff result",
                    evidence_paths=("src/acme/core/repository.py",),
                ),
                lsp_delta_provenance(
                    source_tool="basedpyright",
                    evidence_summary="result includes lsp delta",
                    evidence_paths=("src/acme/core/repository.py",),
                ),
            ),
        ),
    )

    assert view.provenance
    assert view.diagnostics[0].provenance
    assert view.entity_delta.provenance


def test_change_impact_presenter_maps_composed_artifact(npm_repo_root) -> None:
    repository = Workspace(npm_repo_root).repositories[0]
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
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]

    related_test = repository.tests.get_related_tests(
        RelatedTestTarget(repository_rel_path="packages/core/src/index.ts")
    )[0]
    runner = repository.arch.get_runners()[0]
    component = next(
        item for item in repository.arch.get_components() if item.id == "component:npm:@monorepo/core"
    )
    impact = ChangeImpact(
        target_kind="file",
        owner=repository.resolve_owner("component:npm:@monorepo/core"),
        primary_component=component,
        component_context=repository.describe_components(("component:npm:@monorepo/core",))[0],
        file_context=repository.describe_files(("packages/core/src/index.ts",))[0],
        dependent_components=(
            next(item for item in repository.arch.get_components() if item.id == "component:npm:@monorepo/utils"),
        ),
        reference_locations=(
            CodeLocation(
                repository_rel_path="packages/core/src/index.ts",
                line_start=1,
                line_end=13,
                column_start=1,
                column_end=2,
                provenance=(
                    lsp_location_provenance(
                        source_tool="typescript-language-server",
                        repository_rel_path="packages/core/src/index.ts",
                        operation="references",
                    ),
                ),
            ),
        ),
        related_tests=(
            ChangeTestImpact(
                related_test=related_test,
                reason="same_file_context",
                provenance=related_test.provenance,
            ),
        ),
        related_runners=(
            RunnerImpact(
                runner=runner,
                reason="same_component",
                provenance=(
                    ownership_provenance(
                        evidence_summary="runner linked to component",
                        evidence_paths=("packages/core/package.json",),
                    ),
                ),
            ),
        ),
        quality_gates=(
            QualityGateInfo(
                provider_id="npm",
                provider_roles=("quality",),
                applies=True,
                reason="quality provider applies to the target file",
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.QUALITY_TOOL,
                        source_tool="npm",
                        evidence_summary="quality gate derived from provider support",
                        evidence_paths=("packages/core/src/index.ts",),
                    ),
                ),
            ),
        ),
        provenance=(
            ownership_provenance(
                evidence_summary="change analysis anchored to owner",
                evidence_paths=("packages/core/src/index.ts",),
            ),
        ),
    )

    view = ChangeImpactPresenter().change_impact_view(impact)

    assert view.primary_component is not None
    assert view.related_tests[0].provenance
    assert view.related_runners[0].provenance
    assert view.quality_gates[0].provenance
    assert view.provenance
