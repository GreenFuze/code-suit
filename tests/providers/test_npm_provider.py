from __future__ import annotations

from suitcode.core.models import (
    Aggregator,
    Component,
    EntityInfo,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition as DefinitionNode,
)
from suitcode.core.action_models import ActionKind
from suitcode.core.intelligence_models import (
    ComponentDependencyEdge,
    DependencyRef,
    FileRelationshipKind,
    FileRelationshipRef,
    InvariantAccessKind,
    InvariantFindingKind,
    InvariantFindingRef,
    RenderEdgeKind,
    RenderEdgeRef,
    StaticFlowEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.runner_service import RunnerService
from suitcode.core.provenance import SourceKind
from suitcode.core.tests.models import (
    RelatedTestTarget,
    TestExecutionResult as CoreTestExecutionResult,
    TestExecutionStatus as CoreTestExecutionStatus,
)
from suitcode.core.provenance_builders import heuristic_provenance
from suitcode.core.provenance_builders import dependency_graph_provenance
from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.npm import NPMProvider
from suitcode.providers.npm.quality_models import NpmQualityEntityDelta, NpmQualityOperationResult
from suitcode.providers.shared.action_execution import ActionExecutionResult, ActionExecutionStatus
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)
from suitcode.providers.npm.static_analysis_service import NpmStaticAnalysisService
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.runtime_capability_models import RuntimeCapabilityAvailability
from tests.providers.npm.expected_npm_provider_data import (
    EXPECTED_AGGREGATOR_IDS,
    EXPECTED_COMPONENT_IDS,
    EXPECTED_COMPONENT_KINDS,
    EXPECTED_COMPONENT_LANGUAGES,
    EXPECTED_EXTERNAL_PACKAGE_IDS,
    EXPECTED_PACKAGE_MANAGER_IDS,
    EXPECTED_REPRESENTATIVE_FILE_OWNERS,
    EXPECTED_TEST_IDS,
)


def test_architecture_provider_base_contract() -> None:
    assert issubclass(NPMProvider, ArchitectureProviderBase)


def test_action_provider_base_contract() -> None:
    assert issubclass(NPMProvider, ActionProviderBase)


def test_code_provider_base_contract() -> None:
    assert issubclass(NPMProvider, CodeProviderBase)


def test_test_provider_base_contract() -> None:
    assert issubclass(NPMProvider, TestProviderBase)


def test_quality_provider_base_contract() -> None:
    assert issubclass(NPMProvider, QualityProviderBase)


def test_npm_provider_returns_monorepo_components(npm_provider: NPMProvider) -> None:
    components = npm_provider.get_components()
    component_ids = {component.id for component in components}
    component_languages = {
        component.id: component.language.value
        for component in components
        if component.id in EXPECTED_COMPONENT_LANGUAGES
    }
    component_kinds = {
        component.id: component.component_kind.value
        for component in components
        if component.id in EXPECTED_COMPONENT_KINDS
    }

    assert isinstance(components[0], Component)
    assert component_ids == EXPECTED_COMPONENT_IDS
    assert component_languages == EXPECTED_COMPONENT_LANGUAGES
    assert component_kinds == EXPECTED_COMPONENT_KINDS
    assert all(component.provenance for component in components)
    assert all(component.provenance[0].source_kind.value == "manifest" for component in components)


def test_npm_provider_returns_aggregators_runners_and_tests(npm_provider: NPMProvider) -> None:
    aggregators = npm_provider.get_aggregators()
    runners = npm_provider.get_runners()
    tests = npm_provider.get_tests()
    discovered_tests = npm_provider.get_discovered_tests()

    assert all(isinstance(node, Aggregator) for node in aggregators)
    assert {node.id for node in aggregators} == EXPECTED_AGGREGATOR_IDS
    assert any(node.id == "runner:npm:@monorepo/codegen:build" for node in runners)
    assert any(node.id == "runner:npm:@monorepo/codegen:test" for node in runners)
    assert all(node.provenance for node in aggregators)
    assert all(node.provenance for node in runners)
    assert {node.id for node in tests} == EXPECTED_TEST_IDS
    assert all(isinstance(node, Runner) for node in runners)
    assert all(isinstance(node, DefinitionNode) for node in tests)
    assert all(node.provenance for node in tests)
    assert tuple(item.test_definition.id for item in discovered_tests) == tuple(sorted(EXPECTED_TEST_IDS))
    assert all(item.primary_source_kind in {SourceKind.TEST_TOOL, SourceKind.HEURISTIC} for item in discovered_tests)


def test_npm_provider_returns_package_managers_external_packages_and_files(npm_provider: NPMProvider) -> None:
    package_managers = npm_provider.get_package_managers()
    external_packages = npm_provider.get_external_packages()
    files = npm_provider.get_files()

    assert all(isinstance(node, PackageManager) for node in package_managers)
    assert tuple(node.id for node in package_managers) == EXPECTED_PACKAGE_MANAGER_IDS
    assert all(isinstance(node, ExternalPackage) for node in external_packages)
    assert {node.id for node in external_packages} == EXPECTED_EXTERNAL_PACKAGE_IDS
    assert all(node.manager_id == "pkgmgr:npm:root" for node in external_packages)
    assert all(node.provenance for node in package_managers)
    assert all(node.provenance for node in external_packages)

    assert all(isinstance(node, FileInfo) for node in files)
    assert all(node.provenance for node in files)
    owned = {node.repository_rel_path: node.owner_id for node in files}
    assert {path: owned[path] for path in EXPECTED_REPRESENTATIVE_FILE_OWNERS} == EXPECTED_REPRESENTATIVE_FILE_OWNERS


def test_npm_provider_assigns_public_runtime_assets_to_package_owner(tmp_path) -> None:
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

    workspace = Workspace(repo_root)
    repository = workspace.repositories[0]
    owner = repository.get_file_owner("public/runtimes/demo/runtime.js")

    assert owner.owner.id == "component:npm:frontend"


def test_npm_provider_internal_analysis_stays_npm_specific(npm_provider: NPMProvider) -> None:
    assert all(isinstance(item, NpmPackageAnalysis) for item in npm_provider._get_components())
    assert all(isinstance(item, NpmAggregatorAnalysis) for item in npm_provider._get_aggregators())
    assert all(isinstance(item, NpmRunnerAnalysis) for item in npm_provider._get_runners())
    assert all(isinstance(item, NpmTestAnalysis) for item in npm_provider._get_tests())
    assert all(isinstance(item, NpmPackageManagerAnalysis) for item in npm_provider._get_package_managers())
    assert all(isinstance(item, NpmOwnedFileAnalysis) for item in npm_provider._get_files())


def test_npm_provider_uses_fixture_repository_root(npm_repository: Repository) -> None:
    assert npm_repository.root.name == "npm"
    assert npm_repository.provider_ids == ("go", "npm", "python")


def test_npm_provider_get_symbol_returns_entity_info(npm_provider: NPMProvider) -> None:

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="CoreContainer",
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[assignment]
    symbols = npm_provider.get_symbol("Core")

    assert len(symbols) == 1
    assert isinstance(symbols[0], EntityInfo)
    assert symbols[0].id == "entity:packages/core/src/index.ts:class:Core:1-11"
    assert symbols[0].signature == "CoreContainer"
    assert symbols[0].provenance[0].source_kind.value == "lsp"


def test_npm_provider_definition_and_reference_locations_include_provenance(npm_provider: NPMProvider) -> None:
    class _FakeFileSymbolService:
        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (("packages/utils/src/index.ts", 7, 9, 1, 2),)

    npm_provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[assignment]

    definitions = npm_provider.find_definition("packages/core/src/index.ts", 1, 1)
    references = npm_provider.find_references("packages/core/src/index.ts", 1, 1)

    assert definitions[0].provenance[0].source_kind.value == "lsp"
    assert definitions[0].provenance[0].source_tool == "typescript-language-server"
    assert references[0].provenance[0].source_kind.value == "lsp"
    assert references[0].provenance[0].source_tool == "typescript-language-server"


def test_npm_provider_returns_file_relationships_from_provider_service(npm_provider: NPMProvider) -> None:
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

    npm_provider._file_relationship_service = _FakeRelationshipService()  # type: ignore[assignment]

    relationships = npm_provider.get_file_relationships("packages/core/src/index.ts")

    assert len(relationships) == 1
    assert relationships[0].relationship_kind == FileRelationshipKind.IMPORTED_BY
    assert relationships[0].repository_rel_path == "packages/utils/src/index.ts"


def test_npm_provider_returns_render_edges_from_provider_service(npm_provider: NPMProvider) -> None:
    class _FakeRenderEdgeService:
        def get_file_render_edges(self, repository_rel_path: str) -> tuple[RenderEdgeRef, ...]:
            assert repository_rel_path == "packages/core/src/index.tsx"
            return (
                RenderEdgeRef(
                    repository_rel_path="packages/ui/src/Button.tsx",
                    relationship_kind=RenderEdgeKind.RENDERS,
                    line_start=12,
                    column_start=5,
                    prop_names=("label", "onClick"),
                    has_spread_props=False,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved JSX render edge",
                            evidence_paths=("packages/core/src/index.tsx", "packages/ui/src/Button.tsx"),
                        ),
                    ),
                ),
            )

    npm_provider._render_edge_service = _FakeRenderEdgeService()  # type: ignore[assignment]

    edges = npm_provider.get_file_render_edges("packages/core/src/index.tsx")

    assert len(edges) == 1
    assert edges[0].relationship_kind == RenderEdgeKind.RENDERS
    assert edges[0].repository_rel_path == "packages/ui/src/Button.tsx"
    assert edges[0].prop_names == ("label", "onClick")


def test_npm_provider_returns_static_analysis_from_provider_service(npm_provider: NPMProvider) -> None:
    class _FakeStaticAnalysisService:
        def get_file_analysis(self, repository_rel_path: str):
            assert repository_rel_path == "packages/core/src/index.tsx"
            findings = (
                InvariantFindingRef(
                    repository_rel_path="packages/core/src/index.tsx",
                    finding_kind=InvariantFindingKind.MAYBE_MISSING_FIELD_ACCESS,
                    access_kind=InvariantAccessKind.METHOD_CALL,
                    line_start=24,
                    column_start=9,
                    field_name="status",
                    subject_label="integration",
                    declared_type="string | undefined",
                    producer_site_count=0,
                    producer_sites_preview=tuple(),
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found maybe-missing field access",
                            evidence_paths=("packages/core/src/index.tsx",),
                        ),
                    ),
                ),
            )
            flows = (
                StaticFlowEdgeRef(
                    repository_rel_path="packages/core/src/index.tsx",
                    edge_kind=StaticFlowEdgeKind.PRODUCES_VALUE_FOR,
                    line_start=30,
                    column_start=5,
                    source_label="toStateMap",
                    target_label="setState",
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found local flow edge",
                            evidence_paths=("packages/core/src/index.tsx",),
                        ),
                    ),
                ),
            )
            return findings, flows

    npm_provider._static_analysis_service = _FakeStaticAnalysisService()  # type: ignore[assignment]

    findings = npm_provider.get_file_invariant_findings("packages/core/src/index.tsx")
    flows = npm_provider.get_file_local_flow_edges("packages/core/src/index.tsx")

    assert len(findings) == 1
    assert findings[0].field_name == "status"
    assert findings[0].access_kind == InvariantAccessKind.METHOD_CALL
    assert len(flows) == 1
    assert flows[0].source_label == "toStateMap"
    assert flows[0].target_label == "setState"


def test_static_analysis_service_coerces_findings_with_producer_sites() -> None:
    findings = NpmStaticAnalysisService._coerce_findings(
        [
            {
                "path": "packages/core/src/index.tsx",
                "access_kind": "method_call",
                "line_start": 24,
                "column_start": 9,
                "field_name": "status",
                "subject_label": "integration",
                "declared_type": "string | undefined",
                "producer_sites": [
                    {
                        "path": "packages/core/src/index.tsx",
                        "line_start": 12,
                        "column_start": 3,
                        "label": "toStateMap",
                    }
                ],
            }
        ]
    )

    assert len(findings) == 1
    assert findings[0]["producer_sites"][0]["label"] == "toStateMap"


def test_static_analysis_service_detects_optional_field_access_and_local_flow(tmp_path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "tsconfig.json").write_text(
        """
        {
          "compilerOptions": {
            "target": "ES2020",
            "module": "ESNext",
            "moduleResolution": "Node",
            "strict": true
          },
          "include": ["src/**/*"]
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "analysis.ts").write_text(
        """
        type Item = { status?: string };

        function buildItem(): Item {
          return {};
        }

        const next = buildItem();
        export const label = next.status.replace(/_/g, " ");
        """.strip(),
        encoding="utf-8",
    )

    service = NpmStaticAnalysisService(
        repository_root=repo_root,
        attachment_root=repo_root,
    )

    findings, flows = service.get_file_analysis("src/analysis.ts")

    assert any(item.field_name == "status" for item in findings)
    assert any(item.source_label == "buildItem" and item.target_label == "next" for item in flows)
    assert any(item.field_name == "status" and item.producer_site_count >= 1 for item in findings)


def test_static_analysis_service_keeps_optional_field_finding_without_explicit_omission(tmp_path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "tsconfig.json").write_text(
        """
        {
          "compilerOptions": {
            "target": "ES2020",
            "module": "ESNext",
            "moduleResolution": "Node",
            "strict": true
          },
          "include": ["src/**/*"]
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "analysis.ts").write_text(
        """
        type Item = { status?: string };

        function buildItem(): Item {
          return { status: "ready" };
        }

        function formatItem(item: Item): string {
          return item.status.replace(/_/g, " ");
        }

        const next = buildItem();
        export const label = formatItem(next);
        """.strip(),
        encoding="utf-8",
    )

    service = NpmStaticAnalysisService(
        repository_root=repo_root,
        attachment_root=repo_root,
    )

    findings, _ = service.get_file_analysis("src/analysis.ts")

    assert any(item.field_name == "status" for item in findings)
    assert all(item.producer_site_count == 0 for item in findings if item.field_name == "status")


def test_npm_provider_internal_symbol_analysis_stays_npm_specific(npm_provider: NPMProvider) -> None:

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature=None,
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[assignment]

    assert all(isinstance(item, NpmWorkspaceSymbol) for item in npm_provider._get_symbols("Core"))


def test_npm_provider_quality_methods_return_public_results(npm_provider: NPMProvider) -> None:
    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=True,
                success=True,
                message="linted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="after",
            )

        def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="prettier",
                operation="format",
                changed=False,
                success=True,
                message="formatted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=False,
                content_sha_before="same",
                content_sha_after="same",
            )

    npm_provider._quality_service = _FakeQualityService()  # type: ignore[assignment]

    lint_result = npm_provider.lint_file("packages/core/src/index.ts", is_fix=True)
    format_result = npm_provider.format_file("packages/core/src/index.ts")

    assert isinstance(lint_result, QualityFileResult)
    assert isinstance(format_result, QualityFileResult)
    assert lint_result.tool == "eslint"
    assert format_result.tool == "prettier"


def test_repository_intelligence_wraps_registered_npm_provider(npm_repository: Repository) -> None:
    component_ids = {component.id for component in npm_repository.arch.get_components()}
    test_ids = {test.id for test in npm_repository.tests.get_tests()}

    assert EXPECTED_COMPONENT_IDS.issubset(component_ids)
    assert "component:go:native-addon" in component_ids
    assert EXPECTED_TEST_IDS.issubset(test_ids)
    assert npm_repository.provider_ids == ("go", "npm", "python")
    assert npm_repository.quality.provider_ids == ("npm", "python")


def test_repository_code_intelligence_uses_registered_provider(npm_repository: Repository) -> None:
    npm_provider = npm_repository.get_provider("npm")

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="CoreContainer",
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[attr-defined]
    symbols = npm_repository.code.get_symbol("Core")

    assert len(symbols) == 1
    assert symbols[0].id == "entity:packages/core/src/index.ts:class:Core:1-11"


def test_repository_quality_intelligence_dispatches_to_selected_provider(npm_repository: Repository) -> None:
    npm_provider = npm_repository.get_provider("npm")

    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=True,
                success=True,
                message="linted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="after",
            )

        def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="prettier",
                operation="format",
                changed=False,
                success=True,
                message="formatted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=False,
                content_sha_before="same",
                content_sha_after="same",
            )

    npm_provider._quality_service = _FakeQualityService()  # type: ignore[attr-defined]

    lint_result = npm_repository.quality.lint_file("packages/core/src/index.ts", is_fix=True, provider_id="npm")
    format_result = npm_repository.quality.format_file("packages/core/src/index.ts", provider_id="npm")

    assert lint_result.tool == "eslint"
    assert format_result.tool == "prettier"


def test_repository_file_owner_and_files_by_owner(npm_repository: Repository) -> None:
    file_owner = npm_repository.get_file_owner("packages/core/src/index.ts")
    files = npm_repository.list_files_by_owner("component:npm:@monorepo/core")

    assert file_owner.owner.id == "component:npm:@monorepo/core"
    assert any(item.repository_rel_path == "packages/core/src/index.ts" for item in files)


def test_repository_related_tests_for_npm_component_file(npm_repository: Repository) -> None:
    matches = npm_repository.tests.get_related_tests(
        RelatedTestTarget(repository_rel_path="packages/core/src/index.ts")
    )

    assert any(match.test_definition.id == "test:npm:@monorepo/core" for match in matches)
    assert all(match.relation_reason == "same_package" for match in matches)


def test_npm_provider_returns_no_related_tests_for_non_npm_owner(npm_repository: Repository) -> None:
    npm_provider = npm_repository.get_provider("npm")

    matches = npm_provider.get_related_tests(
        RelatedTestTarget(owner_id="component:go:native-addon")
    )

    assert matches == tuple()


def test_npm_provider_returns_component_dependencies_and_dependents(npm_provider: NPMProvider) -> None:
    dependencies = npm_provider.get_component_dependencies("component:npm:@monorepo/utils")
    dependency_edges = npm_provider.get_component_dependency_edges("component:npm:@monorepo/utils")
    dependents = npm_provider.get_component_dependents("component:npm:@monorepo/core")

    assert all(isinstance(item, DependencyRef) for item in dependencies)
    assert all(isinstance(item, ComponentDependencyEdge) for item in dependency_edges)
    assert all(item.source_component_id == "component:npm:@monorepo/utils" for item in dependency_edges)
    assert {item.target_id for item in dependency_edges} == {item.target_id for item in dependencies}
    assert any(item.target_id == "component:npm:@monorepo/core" and item.dependency_scope == "runtime" for item in dependencies)
    assert "component:npm:@monorepo/utils" in dependents


def test_npm_provider_exposes_deterministic_actions(npm_provider: NPMProvider) -> None:
    actions = npm_provider.get_actions()

    assert actions
    assert all(item.provider_id == "npm" for item in actions)
    assert all(item.invocation.argv for item in actions)
    assert all(item.provenance for item in actions)
    assert any(item.kind == ActionKind.RUNNER_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.TEST_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.BUILD_EXECUTION for item in actions)


def test_npm_provider_code_runtime_capabilities_use_resolver(npm_provider: NPMProvider, monkeypatch) -> None:
    class _FakeResolver:
        def resolve(self, repository_root):
            return ("node", "managed-cli.mjs", "--stdio")

        def resolve_initialization_options(self, repository_root):
            return {"tsserver": {"path": "managed-tsserver.js"}}

    monkeypatch.setattr(
        "suitcode.providers.npm.npm_provider.TypeScriptLanguageServerResolver",
        lambda: _FakeResolver(),
    )

    capabilities = npm_provider.get_code_runtime_capabilities()

    assert capabilities.symbol_search.availability == RuntimeCapabilityAvailability.AVAILABLE
    assert capabilities.definitions.availability == RuntimeCapabilityAvailability.AVAILABLE


def test_npm_provider_describe_and_run_test_targets(npm_provider: NPMProvider) -> None:
    description = npm_provider.describe_test_target("test:npm:@monorepo/core")

    assert description.test_definition.id == "test:npm:@monorepo/core"
    assert description.command_argv
    assert description.provenance

    class _FakeExecutionService:
        def run_target(self, target_description, timeout_seconds: int):
            return CoreTestExecutionResult(
                test_id=target_description.test_definition.id,
                status=CoreTestExecutionStatus.PASSED,
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

    npm_provider._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
    results = npm_provider.run_test_targets(("test:npm:@monorepo/core",), timeout_seconds=45)

    assert results[0].test_id == "test:npm:@monorepo/core"
    assert results[0].duration_ms == 45
    assert results[0].warning == description.warning


def test_npm_repository_describe_and_run_runner(npm_repository: Repository) -> None:
    runner_id = npm_repository.arch.get_runners()[0].id
    context = npm_repository.describe_runner(runner_id)

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

    npm_repository._runner_service = RunnerService(  # type: ignore[attr-defined]
        npm_repository,
        action_execution_service=_FakeActionExecutionService(),
    )
    result = npm_repository.run_runner(runner_id, timeout_seconds=16)

    assert result.runner_id == runner_id
    assert result.status.value == "passed"
    assert result.duration_ms == 16
