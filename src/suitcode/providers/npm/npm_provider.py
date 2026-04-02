from __future__ import annotations

import os
import shutil
from dataclasses import replace
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.intelligence_models import FileRelationshipRef
from suitcode.core.intelligence_models import ImplementationFlowStepRef
from suitcode.core.intelligence_models import InvariantFindingRef
from suitcode.core.intelligence_models import RenderEdgeRef
from suitcode.core.intelligence_models import StaticFlowEdgeRef
from suitcode.core.action_models import RepositoryAction
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from suitcode.core.models import (
    Aggregator,
    Component,
    EntityInfo,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
)
from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_builders import manifest_provenance
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.npm.action_service import NpmActionService
from suitcode.providers.npm.quality_models import NpmQualityOperationResult
from suitcode.providers.npm.quality_service import NpmQualityService
from suitcode.providers.npm.quality_translation import NpmQualityTranslator
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmExternalPackageAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)
from suitcode.providers.npm.location_translation import NpmLocationTranslator
from suitcode.providers.npm.file_relationship_service import NpmFileRelationshipService
from suitcode.providers.npm.render_edge_service import NpmRenderEdgeService
from suitcode.providers.npm.static_analysis_service import NpmStaticAnalysisService
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.npm.symbol_service import NpmFileSymbolService, NpmSymbolService
from suitcode.providers.npm.symbol_translation import NpmSymbolTranslator
from suitcode.providers.npm.translation import NpmModelTranslator
from suitcode.providers.npm.workspace_analyzer import NpmWorkspaceAnalyzer
from suitcode.providers.provider_metadata import ProviderAttachmentCandidate, ProviderAttachmentContext
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.shared.code_facade import CodeFacadeMixin
from suitcode.providers.shared.component_index import ComponentIndexBuilder
from suitcode.providers.shared.provider_translation_mixin import ProviderTranslationMixin
from suitcode.providers.shared.actions import ProviderActionSpec, ProviderActionTranslator
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader
from suitcode.providers.shared.package_json.models import PackageJsonWorkspace
from suitcode.providers.shared.test_facade import TestFacadeMixin
from suitcode.providers.shared.test_execution import TestExecutionService
from suitcode.providers.shared.test_target_runtime import DeterministicTestTargetMixin
from suitcode.providers.runtime_capability_models import (
    ActionRuntimeCapabilities,
    CodeRuntimeCapabilities,
    QualityRuntimeCapabilities,
    RuntimeCapability,
    RuntimeCapabilityAvailability,
    TestRuntimeCapabilities,
)
from suitcode.providers.npm.tool_resolution import NpmQualityToolResolver
from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class NPMProvider(
    ProviderTranslationMixin,
    CodeFacadeMixin,
    TestFacadeMixin,
    DeterministicTestTargetMixin,
    ArchitectureProviderBase,
    CodeProviderBase,
    TestProviderBase,
    QualityProviderBase,
    ActionProviderBase,
):
    PROVIDER_ID = "npm"
    DISPLAY_NAME = "npm"
    BUILD_SYSTEMS = ("npm",)
    PROGRAMMING_LANGUAGES = ("javascript", "typescript")

    @classmethod
    def discover_attachments(cls, repository_root: Path) -> tuple[ProviderAttachmentCandidate, ...]:
        root = repository_root.expanduser().resolve()
        manifests: dict[Path, object] = {}
        loader = PackageJsonWorkspaceLoader()
        manifest_loader = loader._manifest_loader  # type: ignore[attr-defined]
        for manifest_path in sorted(root.rglob("package.json")):
            rel_parts = {part.lower() for part in manifest_path.relative_to(root).parts[:-1]}
            if rel_parts.intersection({"node_modules", ".git", ".suit", "dist", "build", ".next"}):
                continue
            try:
                manifest = manifest_loader.load(manifest_path)
            except ValueError:
                continue
            manifests[manifest_path.parent.resolve()] = manifest
        if not manifests:
            return tuple()
        attachments: list[ProviderAttachmentCandidate] = []
        for package_root, manifest in sorted(manifests.items()):
            if cls._covered_by_workspace(package_root, manifests):
                continue
            try:
                loader.load(package_root)
            except ValueError:
                continue
            attachments.append(
                ProviderAttachmentCandidate(
                    provider_id=cls.PROVIDER_ID,
                    attachment_root=package_root,
                    detected_roles=frozenset(
                        {
                            ProviderRole.ARCHITECTURE,
                            ProviderRole.CODE,
                            ProviderRole.TEST,
                            ProviderRole.QUALITY,
                        }
                    ),
                )
            )
        return tuple(attachments)

    @classmethod
    def _covered_by_workspace(cls, package_root: Path, manifests: dict[Path, object]) -> bool:
        for candidate_root, candidate_manifest in manifests.items():
            if candidate_root == package_root:
                continue
            try:
                relative = package_root.relative_to(candidate_root).as_posix()
            except ValueError:
                continue
            workspaces = getattr(candidate_manifest, "workspaces", tuple())
            if not workspaces:
                continue
            if any(PurePosixPath(relative).match(pattern) for pattern in workspaces):
                return True
        return False

    def __init__(self, repository: Repository, attachment: ProviderAttachmentContext) -> None:
        super().__init__(repository, attachment)
        self._workspace_loader = PackageJsonWorkspaceLoader()
        self._translator = NpmModelTranslator()
        self._action_translator = ProviderActionTranslator(provider_id="npm", default_test_tool="jest")
        self._symbol_translator = NpmSymbolTranslator()
        self._location_translator = NpmLocationTranslator()
        self._quality_translator = NpmQualityTranslator(self._symbol_translator)
        self._action_service = NpmActionService()
        self._workspace: PackageJsonWorkspace | None = None
        self._analyzer: NpmWorkspaceAnalyzer | None = None
        self._component_id_index: dict[str, NpmPackageAnalysis] | None = None
        self._dependency_edges_cache: tuple[ComponentDependencyEdge, ...] | None = None
        self._symbol_service: NpmSymbolService | None = None
        self._file_symbol_service: NpmFileSymbolService | None = None
        self._file_relationship_service: NpmFileRelationshipService | None = None
        self._render_edge_service: NpmRenderEdgeService | None = None
        self._static_analysis_service: NpmStaticAnalysisService | None = None
        self._quality_service: NpmQualityService | None = None
        self._test_execution_service: TestExecutionService | None = None

    def get_components(self) -> tuple[Component, ...]:
        return self._translate_sorted(self._get_components(), self._translator.to_component, key=lambda item: item.id)

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return self._translate_sorted(self._get_aggregators(), self._translator.to_aggregator, key=lambda item: item.id)

    def get_runners(self) -> tuple[Runner, ...]:
        return self._translate_sorted(self._get_runners(), self._translator.to_runner, key=lambda item: item.id)

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return self._translate_sorted(
            self._get_package_managers(),
            self._translator.to_package_manager,
            key=lambda item: item.id,
        )

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return self._translate_sorted(
            self._get_external_packages(),
            self._translator.to_external_package,
            key=lambda item: item.id,
        )

    def get_files(self) -> tuple[FileInfo, ...]:
        return self._translate_sorted(self._get_files(), self._translator.to_file_info, key=lambda item: item.id)

    def get_component_dependency_edges(self, component_id: str | None = None) -> tuple[ComponentDependencyEdge, ...]:
        return self._filter_dependency_edges(
            component_id,
            self._all_component_dependency_edges(),
            self._component_analysis_by_id(),
        )

    def get_actions(self) -> tuple[RepositoryAction, ...]:
        return tuple(
            sorted(
                (self._action_translator.to_repository_action(item) for item in self._get_actions()),
                key=lambda item: item.id,
            )
        )

    def get_code_runtime_capabilities(self) -> CodeRuntimeCapabilities:
        resolver = TypeScriptLanguageServerResolver()
        try:
            resolver.resolve(self.attachment_root)
            resolver.resolve_initialization_options(self.attachment_root)
            capability = self._runtime_capability(
                capability_id="npm.code.lsp",
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.LSP,
                source_tool="typescript-language-server",
                summary="repository-local TypeScript language-server tooling is available for npm code intelligence",
            )
        except ValueError as exc:
            capability = self._runtime_capability(
                capability_id="npm.code.lsp",
                availability=RuntimeCapabilityAvailability.DEGRADED,
                source_kind=SourceKind.LSP,
                source_tool="typescript-language-server",
                summary="TypeScript language-server tooling is unavailable for npm code intelligence",
                reason=str(exc),
            )
        return CodeRuntimeCapabilities(
            symbol_search=capability,
            symbols_in_file=capability,
            definitions=capability,
            references=capability,
            implementations=capability,
        )

    def get_test_runtime_capabilities(self) -> TestRuntimeCapabilities:
        discovered_tests = self._get_tests()
        if not discovered_tests:
            unavailable = self._runtime_capability(
                capability_id="npm.tests.discovery",
                availability=RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.HEURISTIC,
                source_tool="jest",
                summary="repository exposes no npm test definitions",
                reason="repository exposes no npm test definitions",
            )
            return TestRuntimeCapabilities(
                discovery=unavailable,
                execution=unavailable.model_copy(update={"capability_id": "npm.tests.execution"}),
            )
        discovery = self._runtime_capability(
            capability_id="npm.tests.discovery",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.MANIFEST,
            source_tool="jest",
            summary="npm test definitions are discoverable from package metadata",
        )
        if self._npm_command_available():
            execution = self._runtime_capability(
                capability_id="npm.tests.execution",
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.MANIFEST,
                source_tool="npm",
                summary="npm command is available for deterministic npm test execution",
            )
        else:
            execution = self._runtime_capability(
                capability_id="npm.tests.execution",
                availability=RuntimeCapabilityAvailability.DEGRADED,
                source_kind=SourceKind.MANIFEST,
                source_tool="npm",
                summary="npm command is unavailable for deterministic npm test execution",
                reason=f"npm executable was not found for repository `{self.attachment_root}`",
            )
        return TestRuntimeCapabilities(discovery=discovery, execution=execution)

    def get_quality_runtime_capabilities(
        self,
        repository_rel_paths: tuple[str, ...] | None = None,
    ) -> QualityRuntimeCapabilities:
        relevant_paths = tuple(
            path
            for path in (repository_rel_paths or self._quality_paths())
            if Path(path).suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}
        )
        if not relevant_paths:
            unavailable = self._runtime_capability(
                capability_id="npm.quality.lint",
                availability=RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.QUALITY_TOOL,
                source_tool="eslint",
                summary="npm quality provider has no supported JS/TS files",
                reason="npm quality provider has no supported JS/TS files",
            )
            return QualityRuntimeCapabilities(
                lint=unavailable,
                format=unavailable.model_copy(
                    update={
                        "capability_id": "npm.quality.format",
                        "source_tool": "prettier",
                    }
                ),
            )
        resolver = NpmQualityToolResolver(self.repository)
        first_path = (self.repository.root / relevant_paths[0]).resolve()
        lint_capability = self._quality_capability(
            capability_id="npm.quality.lint",
            source_tool="eslint",
            summary="eslint is resolvable for npm quality operations",
            resolve=lambda: resolver.resolve_linter(first_path),
        )
        format_capability = self._quality_capability(
            capability_id="npm.quality.format",
            source_tool="prettier",
            summary="prettier is resolvable for npm quality operations",
            resolve=lambda: resolver.resolve_formatter(first_path),
        )
        return QualityRuntimeCapabilities(lint=lint_capability, format=format_capability)

    def get_action_runtime_capabilities(self) -> ActionRuntimeCapabilities:
        runners = self._get_runners()
        tests = self._get_tests()
        has_build_runner = any(runner.script_name == "build" for runner in runners)
        return ActionRuntimeCapabilities(
            tests=self.get_test_runtime_capabilities().execution.model_copy(update={"capability_id": "npm.actions.tests"}),
            builds=self._runtime_capability(
                capability_id="npm.actions.builds",
                availability=RuntimeCapabilityAvailability.AVAILABLE if has_build_runner else RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.MANIFEST,
                source_tool="npm",
                summary="npm build action capability derived from package build scripts",
                reason=None if has_build_runner else "repository exposes no npm build scripts",
            ),
            runners=self._runtime_capability(
                capability_id="npm.actions.runners",
                availability=RuntimeCapabilityAvailability.AVAILABLE if runners else RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.MANIFEST,
                source_tool="npm",
                summary="npm runner action capability derived from package scripts",
                reason=None if runners else "repository exposes no npm runner scripts",
            ),
        )

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        discovered_tests = self.get_discovered_tests()
        if target.owner_id is not None:
            owner = self.repository.resolve_owner(target.owner_id)
            if owner.kind == "test_definition":
                matches = [item for item in discovered_tests if item.test_definition.id == target.owner_id]
                if not matches:
                    raise ValueError(f"test owner id could not be resolved: `{target.owner_id}`")
                return (
                    RelatedTestMatch(
                        test_definition=matches[0].test_definition,
                        relation_reason="same_owner",
                        matched_owner_id=target.owner_id,
                    ),
                )
            if owner.kind != "component":
                return tuple()
            package_root = self._package_root_for_owner(owner.id)
            if package_root is None:
                return tuple()
            return self._tests_for_package_root(package_root, matched_owner_id=owner.id)

        if target.repository_rel_path is None:
            raise ValueError("related test target must include `repository_rel_path` when `owner_id` is not provided")
        owner_info = self.repository.get_file_owner(target.repository_rel_path)
        if owner_info.owner.kind == "test_definition":
            matches = [
                item for item in discovered_tests if target.repository_rel_path in item.test_definition.test_files
            ]
            if not matches:
                raise ValueError(f"test-owned file could not be resolved to a test definition: `{target.repository_rel_path}`")
            return tuple(
                RelatedTestMatch(
                    test_definition=discovered_test.test_definition,
                    relation_reason="same_owner",
                    matched_owner_id=discovered_test.test_definition.id,
                    matched_repository_rel_path=target.repository_rel_path,
                )
                for discovered_test in matches
            )
        if owner_info.owner.kind != "component":
            return tuple()
        package_root = self._package_root_for_file(target.repository_rel_path)
        if package_root is None:
            return tuple()
        return self._tests_for_package_root(package_root, matched_owner_id=owner_info.owner.id, matched_repository_rel_path=target.repository_rel_path)

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._lint_file(repository_rel_path, is_fix))

    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._format_file(repository_rel_path))

    def _load_workspace(self) -> PackageJsonWorkspace:
        if self._workspace is None:
            self._workspace = self._workspace_loader.load(self.attachment_root)
        return self._workspace

    def _build_analyzer(self) -> NpmWorkspaceAnalyzer:
        if self._analyzer is None:
            self._analyzer = NpmWorkspaceAnalyzer(self._load_workspace())
        return self._analyzer

    def _get_components(self) -> tuple[NpmPackageAnalysis, ...]:
        return tuple(self._rebase_component(item) for item in self._build_analyzer().analyze_components())

    def _get_aggregators(self) -> tuple[NpmAggregatorAnalysis, ...]:
        return tuple(self._rebase_aggregator(item) for item in self._build_analyzer().analyze_aggregators())

    def _get_runners(self) -> tuple[NpmRunnerAnalysis, ...]:
        return tuple(self._rebase_runner(item) for item in self._build_analyzer().analyze_runners())

    def _get_tests(self) -> tuple[NpmTestAnalysis, ...]:
        return tuple(self._rebase_test(item) for item in self._build_analyzer().analyze_tests())

    def _get_package_managers(self) -> tuple[NpmPackageManagerAnalysis, ...]:
        return tuple(self._rebase_package_manager(item) for item in self._build_analyzer().analyze_package_managers())

    def _get_external_packages(self) -> tuple[NpmExternalPackageAnalysis, ...]:
        return tuple(self._rebase_external_package(item) for item in self._build_analyzer().analyze_external_packages())

    def _get_files(self) -> tuple[NpmOwnedFileAnalysis, ...]:
        return tuple(self._rebase_file(item) for item in self._build_analyzer().analyze_files())

    def _get_actions(self) -> tuple[ProviderActionSpec, ...]:
        return self._action_service.discover(
            components=self._get_components(),
            runners=self._get_runners(),
            tests=self._get_tests(),
        )

    def _build_symbol_service(self) -> NpmSymbolService:
        if self._symbol_service is None:
            self._symbol_service = NpmSymbolService(self.repository, workspace_loader=self._workspace_loader)
        return self._symbol_service

    def _build_file_symbol_service(self) -> NpmFileSymbolService:
        if self._file_symbol_service is None:
            self._file_symbol_service = NpmFileSymbolService(self.repository, workspace_loader=self._workspace_loader)
        return self._file_symbol_service

    def _build_file_relationship_service(self) -> NpmFileRelationshipService:
        if self._file_relationship_service is None:
            self._file_relationship_service = NpmFileRelationshipService(
                repository_root=self.repository.root,
                attachment_root=self.attachment_root,
            )
        return self._file_relationship_service

    def _build_render_edge_service(self) -> NpmRenderEdgeService:
        if self._render_edge_service is None:
            self._render_edge_service = NpmRenderEdgeService(
                repository_root=self.repository.root,
                attachment_root=self.attachment_root,
            )
        return self._render_edge_service

    def _build_static_analysis_service(self) -> NpmStaticAnalysisService:
        if self._static_analysis_service is None:
            self._static_analysis_service = NpmStaticAnalysisService(
                repository_root=self.repository.root,
                attachment_root=self.attachment_root,
            )
        return self._static_analysis_service

    def _get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
        return self._build_symbol_service().get_symbols(query, is_case_sensitive=is_case_sensitive)

    def _build_quality_service(self) -> NpmQualityService:
        if self._quality_service is None:
            self._quality_service = NpmQualityService(self.repository)
        return self._quality_service

    def _build_test_execution_service(self) -> TestExecutionService:
        if self._test_execution_service is None:
            self._test_execution_service = TestExecutionService(
                repository_root=self.repository.root,
                suit_dir=self.repository.suit_dir,
            )
        return self._test_execution_service

    def _lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
        return self._build_quality_service().lint_file(repository_rel_path, is_fix)

    def _format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
        return self._build_quality_service().format_file(repository_rel_path)

    def _package_root_for_file(self, repository_rel_path: str) -> str | None:
        normalized = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
        for package in self._load_workspace().packages:
            package_root = self._rebase_path(package.repository_rel_path)
            if not package_root:
                return package_root
            if normalized == package_root or normalized.startswith(f"{package_root}/"):
                return package_root
        return None

    def _package_root_for_owner(self, owner_id: str) -> str | None:
        for component in self._get_components():
            translated = self._translator.to_component(component)
            if translated.id == owner_id:
                return component.package_path
        return None

    def _tests_for_package_root(
        self,
        package_root: str,
        matched_owner_id: str | None = None,
        matched_repository_rel_path: str | None = None,
    ) -> tuple[RelatedTestMatch, ...]:
        discovered_tests = self.get_discovered_tests()
        return tuple(
            RelatedTestMatch(
                test_definition=discovered_test.test_definition,
                relation_reason="same_package",
                matched_owner_id=matched_owner_id,
                matched_repository_rel_path=matched_repository_rel_path,
            )
            for discovered_test in discovered_tests
            if any(
                (not package_root and bool(test_file))
                or test_file.startswith(f"{package_root}/")
                or test_file == package_root
                for test_file in discovered_test.test_definition.test_files
            )
        )

    def _component_analysis_by_id(self) -> dict[str, NpmPackageAnalysis]:
        if self._component_id_index is None:
            self._component_id_index = {
                key: value
                for key, value in ComponentIndexBuilder.build(
                    self._get_components(),
                    lambda analysis: self._translator.to_component(analysis).id,
                    lambda component_id: f"duplicate npm component id detected: `{component_id}`",
                ).items()
            }
        return self._component_id_index

    def _all_component_dependency_edges(self) -> tuple[ComponentDependencyEdge, ...]:
        if self._dependency_edges_cache is None:
            component_index = self._component_analysis_by_id()
            local_components = {
                analysis.package_name: translated_component_id
                for translated_component_id, analysis in component_index.items()
            }
            external_packages = {
                item.package_name: self._translator.to_external_package(item).id
                for item in self._get_external_packages()
            }
            edges: list[ComponentDependencyEdge] = []
            for source_component_id, analysis in component_index.items():
                scoped_dependencies = (
                    ("runtime", analysis.manifest.dependencies.dependencies),
                    ("dev", analysis.manifest.dependencies.dev_dependencies),
                    ("peer", analysis.manifest.dependencies.peer_dependencies),
                    ("optional", analysis.manifest.dependencies.optional_dependencies),
                )
                for dependency_scope, dependencies in scoped_dependencies:
                    for dependency_name in sorted(dependencies):
                        if dependency_name in local_components:
                            edges.append(
                                ComponentDependencyEdge(
                                    source_component_id=source_component_id,
                                    target_id=local_components[dependency_name],
                                    target_kind="component",
                                    dependency_scope=dependency_scope,
                                    provenance=(
                                        manifest_provenance(
                                            evidence_summary="derived from workspace package.json dependency metadata",
                                            evidence_paths=(analysis.manifest_path,),
                                        ),
                                    ),
                                )
                            )
                            continue
                        target_id = external_packages.get(dependency_name)
                        if target_id is None:
                            raise ValueError(
                                f"workspace dependency `{dependency_name}` could not be resolved for component `{source_component_id}`"
                            )
                        edges.append(
                            ComponentDependencyEdge(
                                source_component_id=source_component_id,
                                target_id=target_id,
                                target_kind="external_package",
                                dependency_scope=dependency_scope,
                                provenance=(
                                    manifest_provenance(
                                        evidence_summary="derived from workspace package.json dependency metadata",
                                        evidence_paths=(analysis.manifest_path,),
                                    ),
                                ),
                            )
                        )
            self._dependency_edges_cache = tuple(
                sorted(
                    edges,
                    key=lambda item: (
                        item.source_component_id,
                        item.target_kind,
                        item.target_id,
                        item.dependency_scope,
                    ),
                )
            )
        return self._dependency_edges_cache

    def _list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[NpmWorkspaceSymbol, ...]:
        return self._build_file_symbol_service().list_file_symbols(
            repository_rel_path,
            query=query,
            is_case_sensitive=is_case_sensitive,
        )

    def _find_definition_locations(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._build_file_symbol_service().find_definition(repository_rel_path, line, column)

    def _find_reference_locations(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._build_file_symbol_service().find_references(
            repository_rel_path,
            line,
            column,
            include_definition=include_definition,
        )

    def _find_implementation_locations(self, repository_rel_path: str, line: int, column: int) -> tuple[tuple[str, int, int, int, int], ...]:
        return self._build_file_symbol_service().find_implementations(repository_rel_path, line, column)

    def get_file_relationships(self, repository_rel_path: str) -> tuple[FileRelationshipRef, ...]:
        try:
            return self._build_file_relationship_service().get_file_relationships(repository_rel_path)
        except ValueError:
            return tuple()

    def get_file_render_edges(self, repository_rel_path: str) -> tuple[RenderEdgeRef, ...]:
        try:
            return self._build_render_edge_service().get_file_render_edges(repository_rel_path)
        except ValueError:
            return tuple()

    def get_file_invariant_findings(self, repository_rel_path: str) -> tuple[InvariantFindingRef, ...]:
        try:
            findings, _ = self._build_static_analysis_service().get_file_analysis(repository_rel_path)
            return findings
        except ValueError:
            return tuple()

    def get_file_local_flow_edges(self, repository_rel_path: str) -> tuple[StaticFlowEdgeRef, ...]:
        try:
            _, edges = self._build_static_analysis_service().get_file_analysis(repository_rel_path)
            return edges
        except ValueError:
            return tuple()

    def get_file_implementation_flow_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        try:
            return self._build_static_analysis_service().get_file_implementation_flow_steps(repository_rel_path)
        except ValueError:
            return tuple()

    def _to_entity_info(self, symbol: object) -> EntityInfo:
        return self._symbol_translator.to_entity_info(symbol)

    def _to_code_location(
        self,
        location: tuple[str, int, int, int, int],
        *,
        operation: str,
    ):
        return self._location_translator.to_code_location(location, operation=operation)

    def _get_tests_internal(self) -> tuple[NpmTestAnalysis, ...]:
        return self._get_tests()

    def _to_discovered_test_definition(self, test_analysis: object):
        return self._translator.to_discovered_test_definition(test_analysis)

    def _quality_paths(self) -> tuple[str, ...]:
        return tuple(sorted(file_info.repository_rel_path for file_info in self.get_files()))

    @staticmethod
    def _runtime_capability(
        *,
        capability_id: str,
        availability: RuntimeCapabilityAvailability,
        source_kind: SourceKind,
        source_tool: str | None,
        summary: str,
        reason: str | None = None,
    ) -> RuntimeCapability:
        return RuntimeCapability(
            capability_id=capability_id,
            availability=availability,
            source_kind=source_kind,
            source_tool=source_tool,
            reason=reason,
            provenance=(
                derived_summary_provenance(
                    source_kind=source_kind,
                    source_tool=source_tool,
                    evidence_summary=summary if reason is None else f"{summary}: {reason}",
                    evidence_paths=tuple(),
                ),
            ),
        )

    def _quality_capability(
        self,
        *,
        capability_id: str,
        source_tool: str,
        summary: str,
        resolve,
    ) -> RuntimeCapability:
        try:
            resolve()
            return self._runtime_capability(
                capability_id=capability_id,
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.QUALITY_TOOL,
                source_tool=source_tool,
                summary=summary,
            )
        except ValueError as exc:
            return self._runtime_capability(
                capability_id=capability_id,
                availability=RuntimeCapabilityAvailability.DEGRADED,
                source_kind=SourceKind.QUALITY_TOOL,
                source_tool=source_tool,
                summary=f"{source_tool} is unavailable for npm quality operations",
                reason=str(exc),
            )

    @staticmethod
    def _npm_command_available() -> bool:
        candidates = ("npm.cmd", "npm.exe", "npm") if os.name == "nt" else ("npm",)
        return any(shutil.which(candidate) is not None for candidate in candidates)

    def _rebase_component(self, analysis: NpmPackageAnalysis) -> NpmPackageAnalysis:
        return replace(
            analysis,
            package_path=self._rebase_path(analysis.package_path),
            manifest_path=self._rebase_path(analysis.manifest_path),
            source_roots=self._rebase_paths(analysis.source_roots),
            package_owned_paths=self._rebase_paths(analysis.package_owned_paths),
            artifact_paths=self._rebase_paths(analysis.artifact_paths),
        )

    def _rebase_aggregator(self, analysis: NpmAggregatorAnalysis) -> NpmAggregatorAnalysis:
        return replace(
            analysis,
            package_path=self._rebase_path(analysis.package_path),
            manifest_path=self._rebase_path(analysis.manifest_path),
        )

    def _rebase_runner(self, analysis: NpmRunnerAnalysis) -> NpmRunnerAnalysis:
        return replace(
            analysis,
            package_path=self._rebase_path(analysis.package_path),
            cwd=self._rebase_optional_path(analysis.cwd),
            referenced_files=self._rebase_paths(analysis.referenced_files),
        )

    def _rebase_test(self, analysis: NpmTestAnalysis) -> NpmTestAnalysis:
        return replace(
            analysis,
            package_path=self._rebase_path(analysis.package_path),
            test_files=self._rebase_paths(analysis.test_files),
            evidence_paths=self._rebase_paths(analysis.evidence_paths),
        )

    def _rebase_package_manager(self, analysis: NpmPackageManagerAnalysis) -> NpmPackageManagerAnalysis:
        return replace(
            analysis,
            node_id=self._rebase_manager_id(analysis.node_id),
            config_path=self._rebase_optional_path(analysis.config_path),
            owned_files=self._rebase_paths(analysis.owned_files),
        )

    def _rebase_external_package(self, analysis: NpmExternalPackageAnalysis) -> NpmExternalPackageAnalysis:
        return replace(
            analysis,
            manager_id=self._rebase_manager_id(analysis.manager_id),
            evidence_paths=self._rebase_paths(analysis.evidence_paths),
        )

    def _rebase_file(self, analysis: NpmOwnedFileAnalysis) -> NpmOwnedFileAnalysis:
        owner_id = analysis.owner_id
        if owner_id.startswith("pkgmgr:npm:"):
            owner_id = self._rebase_manager_id(owner_id)
        return replace(
            analysis,
            repository_rel_path=self._rebase_path(analysis.repository_rel_path),
            owner_id=owner_id,
        )

    def _rebase_paths(self, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self._rebase_path(item) for item in values)

    def _rebase_optional_path(self, value: str | None) -> str | None:
        if value is None:
            return None
        rebased = self._rebase_path(value)
        return rebased or None

    def _rebase_manager_id(self, manager_id: str) -> str:
        if not self.attachment_root_rel_path or self.attachment_root_rel_path == ".":
            return manager_id
        return f"{manager_id}:{self.attachment_root_rel_path}"

    def _rebase_path(self, value: str) -> str:
        normalized = value.replace("\\", "/").strip().removeprefix("./")
        if normalized == ".":
            normalized = ""
        attachment_root_rel_path = self.attachment_root_rel_path.strip().removesuffix("/")
        if not attachment_root_rel_path or attachment_root_rel_path == ".":
            return normalized
        if not normalized:
            return attachment_root_rel_path
        return f"{attachment_root_rel_path}/{normalized}"
