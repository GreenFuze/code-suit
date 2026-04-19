from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.code.models import CodeLocation
from suitcode.core.models import Aggregator, Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition, TestFramework
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import (
    derived_summary_provenance,
    manifest_node_provenance,
    ownership_node_provenance,
    test_tool_provenance,
)
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, RelatedTestTarget
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.go.action_service import GoActionService
from suitcode.providers.go.implementation_service import GoImplementationService
from suitcode.providers.go.location_translation import GoLocationTranslator
from suitcode.providers.go.lsp_resolution import GoplsResolver
from suitcode.providers.go.models import GoPackageAnalysis, GoPackageManagerAnalysis, GoTestAnalysis
from suitcode.providers.go.symbol_models import GoWorkspaceSymbol
from suitcode.providers.go.symbol_service import GoFileSymbolService, GoSymbolService
from suitcode.providers.go.symbol_translation import GoSymbolTranslator
from suitcode.providers.go.structural_symbol_service import GoStructuralSymbolService
from suitcode.providers.go.workspace_analyzer import GoWorkspaceAnalyzer
from suitcode.providers.shared.structural_symbols import structural_symbols_to_entities
from suitcode.providers.provider_metadata import ProviderAttachmentCandidate, ProviderAttachmentContext
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import (
    ActionRuntimeCapabilities,
    CodeRuntimeCapabilities,
    RuntimeCapability,
    RuntimeCapabilityAvailability,
    TestRuntimeCapabilities,
)
from suitcode.providers.shared.actions import ProviderActionSpec, ProviderActionTranslator
from suitcode.providers.shared.code_facade import CodeFacadeMixin
from suitcode.providers.shared.component_index import ComponentIndexBuilder
from suitcode.providers.shared.provider_translation_mixin import ProviderTranslationMixin
from suitcode.providers.shared.test_execution import TestExecutionService
from suitcode.providers.shared.test_facade import TestFacadeMixin
from suitcode.providers.shared.test_target_runtime import DeterministicTestTargetMixin
from suitcode.providers.test_provider_base import TestProviderBase

if TYPE_CHECKING:
    from suitcode.core.action_models import RepositoryAction
    from suitcode.core.repository import Repository


class GoProvider(
    ProviderTranslationMixin,
    CodeFacadeMixin,
    TestFacadeMixin,
    DeterministicTestTargetMixin,
    ArchitectureProviderBase,
    CodeProviderBase,
    TestProviderBase,
    ActionProviderBase,
):
    PROVIDER_ID = 'go'
    DISPLAY_NAME = 'go'
    BUILD_SYSTEMS = ('go',)
    PROGRAMMING_LANGUAGES = ('go',)

    @classmethod
    def discover_attachments(cls, repository_root: Path) -> tuple[ProviderAttachmentCandidate, ...]:
        root = repository_root.expanduser().resolve()
        module_roots = GoWorkspaceAnalyzer.discover_module_roots(root)
        if not module_roots:
            return tuple()
        attachment_roots = tuple(
            module_root
            for module_root in module_roots
            if not any(parent != module_root and module_root.is_relative_to(parent) for parent in module_roots)
        )
        return tuple(
            ProviderAttachmentCandidate(
                provider_id=cls.PROVIDER_ID,
                attachment_root=attachment_root,
                detected_roles=frozenset({ProviderRole.ARCHITECTURE, ProviderRole.CODE, ProviderRole.TEST}),
            )
            for attachment_root in attachment_roots
        )

    def __init__(self, repository: Repository, attachment: ProviderAttachmentContext) -> None:
        super().__init__(repository, attachment)
        self._module_roots = GoWorkspaceAnalyzer.discover_module_roots(self.attachment_root)
        if not self._module_roots:
            raise ValueError(f'go provider requires one or more go.mod files and no go.work under `{self.attachment_root}`')
        self._analyzer = GoWorkspaceAnalyzer(self.attachment_root)
        self._action_service = GoActionService()
        self._action_translator = ProviderActionTranslator(provider_id='go', default_test_tool='go test')
        self._symbol_translator = GoSymbolTranslator()
        self._location_translator = GoLocationTranslator()
        self._analysis_cache = None
        self._external_package_analysis_cache: tuple | None = None
        self._component_id_index: dict[str, GoPackageAnalysis] | None = None
        self._dependency_edges_cache: tuple[ComponentDependencyEdge, ...] | None = None
        self._test_execution_service: TestExecutionService | None = None
        self._tests_cache: tuple[GoTestAnalysis, ...] | None = None
        self._symbol_service: GoSymbolService | None = None
        self._file_symbol_service: GoFileSymbolService | None = None
        self._structural_symbol_service: GoStructuralSymbolService | None = None
        self._implementation_service: GoImplementationService | None = None
        self._tests_lock = Lock()

    def get_components(self) -> tuple[Component, ...]:
        return self._translate_sorted(self._get_components(), self._to_component, key=lambda item: item.id)

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return tuple()

    def get_runners(self) -> tuple[Runner, ...]:
        return tuple()

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return self._translate_sorted(self._analysis().package_managers, self._to_package_manager, key=lambda item: item.id)

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return self._translate_sorted(self._external_package_analyses(), self._to_external_package, key=lambda item: item.id)

    def get_files(self) -> tuple[FileInfo, ...]:
        return self._translate_sorted(self._analysis().files, self._to_file_info, key=lambda item: item.id)

    def get_component_dependency_edges(self, component_id: str | None = None) -> tuple[ComponentDependencyEdge, ...]:
        return self._filter_dependency_edges(component_id, self._all_component_dependency_edges(), self._component_analysis_by_id())

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        discovered_tests = self.get_discovered_tests()
        if not discovered_tests:
            return tuple()
        if target.owner_id is not None:
            owner = self.repository.resolve_owner(target.owner_id)
            if owner.kind == 'test_definition':
                matches = [item for item in discovered_tests if item.test_definition.id == target.owner_id]
                if not matches:
                    raise ValueError(f'test owner id could not be resolved: `{target.owner_id}`')
                return (
                    RelatedTestMatch(
                        test_definition=matches[0].test_definition,
                        relation_reason='same_owner',
                        matched_owner_id=target.owner_id,
                    ),
                )
            if owner.kind != 'component':
                return tuple()
            return tuple(
                RelatedTestMatch(
                    test_definition=item.test_definition,
                    relation_reason='same_component',
                    matched_owner_id=target.owner_id,
                )
                for item in discovered_tests
                if item.test_definition.id == self._test_id_for_component(owner.id)
            )
        owner_info = self.repository.get_file_owner(target.repository_rel_path)
        if owner_info.owner.kind != 'component':
            return tuple()
        test_id = self._test_id_for_component(owner_info.owner.id)
        return tuple(
            RelatedTestMatch(
                test_definition=item.test_definition,
                relation_reason='same_component',
                matched_owner_id=owner_info.owner.id,
                matched_repository_rel_path=target.repository_rel_path,
            )
            for item in discovered_tests
            if item.test_definition.id == test_id
        )

    def get_code_runtime_capabilities(self) -> CodeRuntimeCapabilities:
        resolver = GoplsResolver()
        try:
            resolver.resolve(self.attachment_root)
            capability = self._runtime_capability(
                capability_id="go.code.lsp",
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.LSP,
                source_tool="gopls",
                summary="gopls is available for deterministic Go code intelligence",
            )
        except ValueError as exc:
            capability = self._runtime_capability(
                capability_id="go.code.lsp",
                availability=RuntimeCapabilityAvailability.DEGRADED,
                source_kind=SourceKind.LSP,
                source_tool="gopls",
                summary="gopls is unavailable for deterministic Go code intelligence",
                reason=str(exc),
            )
        structural_available = shutil.which("go") is not None
        return CodeRuntimeCapabilities(
            structural_symbols=self._runtime_capability(
                capability_id="go.code.structural_symbols",
                availability=(
                    RuntimeCapabilityAvailability.AVAILABLE
                    if structural_available
                    else RuntimeCapabilityAvailability.DEGRADED
                ),
                source_kind=SourceKind.SYNTAX,
                source_tool="go/parser",
                summary="Go structural symbols are available from go/parser without gopls",
                reason=None if structural_available else "go executable is unavailable for go/parser structural analysis",
            ),
            symbol_search=capability,
            symbols_in_file=capability,
            definitions=capability,
            references=capability,
            implementations=capability,
        )

    def get_actions(self) -> tuple['RepositoryAction', ...]:
        return tuple(
            sorted(
                (self._action_translator.to_repository_action(item) for item in self._get_actions()),
                key=lambda item: item.id,
            )
        )

    def get_test_runtime_capabilities(self) -> TestRuntimeCapabilities:
        go_available = shutil.which('go') is not None
        tests = self._get_tests_internal() if go_available else tuple()
        if go_available and tests:
            discovery = self._runtime_capability(
                capability_id='go.tests.discovery',
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.TEST_TOOL,
                source_tool='go test',
                summary='go package-level test discovery is available from go package analysis',
            )
            execution = self._runtime_capability(
                capability_id='go.tests.execution',
                availability=RuntimeCapabilityAvailability.AVAILABLE,
                source_kind=SourceKind.TEST_TOOL,
                source_tool='go test',
                summary='deterministic go test execution is available',
            )
            return TestRuntimeCapabilities(discovery=discovery, execution=execution)
        reason = 'go executable is unavailable or repository exposes no package-level Go tests'
        discovery = self._runtime_capability(
            capability_id='go.tests.discovery',
            availability=RuntimeCapabilityAvailability.UNAVAILABLE,
            source_kind=SourceKind.TEST_TOOL,
            source_tool='go test',
            summary='go package-level test discovery is unavailable',
            reason=reason,
        )
        execution = self._runtime_capability(
            capability_id='go.tests.execution',
            availability=RuntimeCapabilityAvailability.UNAVAILABLE,
            source_kind=SourceKind.TEST_TOOL,
            source_tool='go test',
            summary='deterministic go test execution is unavailable',
            reason=reason,
        )
        return TestRuntimeCapabilities(discovery=discovery, execution=execution)

    def get_action_runtime_capabilities(self) -> ActionRuntimeCapabilities:
        go_available = shutil.which('go') is not None
        has_builds = any(component.is_main for component in self._get_components()) if go_available else False
        test_caps = self.get_test_runtime_capabilities()
        return ActionRuntimeCapabilities(
            tests=test_caps.execution.model_copy(update={'capability_id': 'go.actions.tests'}),
            builds=self._runtime_capability(
                capability_id='go.actions.builds',
                availability=RuntimeCapabilityAvailability.AVAILABLE if go_available and has_builds else RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.MANIFEST,
                source_tool='go list',
                summary='go build action capability derived from buildable main packages',
                reason=None if go_available and has_builds else 'go executable is unavailable or repository exposes no buildable main packages',
            ),
            runners=self._runtime_capability(
                capability_id='go.actions.runners',
                availability=RuntimeCapabilityAvailability.UNAVAILABLE,
                source_kind=SourceKind.HEURISTIC,
                source_tool='go',
                summary='go runner actions are unavailable in phase 2',
                reason='go runner actions are not implemented in phase 2',
            ),
        )

    def _analysis(self):
        if self._analysis_cache is None:
            self._analysis_cache = self._rebase_workspace_analysis(self._analyzer.analyze())
        return self._analysis_cache

    def _build_symbol_service(self) -> GoSymbolService:
        if self._symbol_service is None:
            self._symbol_service = GoSymbolService(
                self.repository,
                attachment_root=self.attachment_root,
                attachment_root_rel_path=self.attachment_root_rel_path,
            )
        return self._symbol_service

    def _build_file_symbol_service(self) -> GoFileSymbolService:
        if self._file_symbol_service is None:
            self._file_symbol_service = GoFileSymbolService(
                self.repository,
                attachment_root=self.attachment_root,
                attachment_root_rel_path=self.attachment_root_rel_path,
            )
        return self._file_symbol_service

    def _build_implementation_service(self) -> GoImplementationService:
        if self._implementation_service is None:
            self._implementation_service = GoImplementationService(
                repository_root=self.repository.root,
                attachment_root=self.attachment_root,
                attachment_root_rel_path=self.attachment_root_rel_path,
                symbol_service=self._build_file_symbol_service(),
            )
        return self._implementation_service

    def _build_structural_symbol_service(self) -> GoStructuralSymbolService:
        if self._structural_symbol_service is None:
            self._structural_symbol_service = GoStructuralSymbolService(
                repository_root=self.repository.root,
                attachment_root=self.attachment_root,
                attachment_root_rel_path=self.attachment_root_rel_path,
            )
        return self._structural_symbol_service

    def _build_test_execution_service(self) -> TestExecutionService:
        if self._test_execution_service is None:
            self._test_execution_service = TestExecutionService(repository_root=self.repository.root, suit_dir=self.repository.suit_dir)
        return self._test_execution_service

    def _get_components(self) -> tuple[GoPackageAnalysis, ...]:
        return self._analysis().components

    def _get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[GoWorkspaceSymbol, ...]:
        return self._build_symbol_service().get_symbols(query, is_case_sensitive=is_case_sensitive)

    def list_structural_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        try:
            symbols = self._build_structural_symbol_service().list_file_symbols(
                repository_rel_path,
                query=query,
                is_case_sensitive=is_case_sensitive,
            )
        except (OSError, subprocess.CalledProcessError, ValueError):
            return tuple()
        return structural_symbols_to_entities(
            symbols,
            source_tool="go/parser",
            evidence_summary="discovered from Go syntax structural symbol analysis",
        )

    def _list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[GoWorkspaceSymbol, ...]:
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

    def get_file_implementation_locations(self, repository_rel_path: str) -> tuple[CodeLocation, ...]:
        return tuple(
            self._to_code_location(item, operation="implementation")
            for item in self._build_implementation_service().get_file_implementation_locations(repository_rel_path)
        )

    def _get_actions(self) -> tuple[ProviderActionSpec, ...]:
        return self._action_service.discover(
            components=self._get_components(),
            tests=self._get_tests_internal(),
        )

    def _component_analysis_by_id(self) -> dict[str, GoPackageAnalysis]:
        if self._component_id_index is None:
            self._component_id_index = {
                key: value
                for key, value in ComponentIndexBuilder.build(
                    self._get_components(),
                    lambda analysis: self._component_id(analysis.import_path),
                    lambda component_id: f'duplicate go component id detected: `{component_id}`',
                ).items()
            }
        return self._component_id_index

    def _all_component_dependency_edges(self) -> tuple[ComponentDependencyEdge, ...]:
        if self._dependency_edges_cache is None:
            local_component_ids = {analysis.import_path: self._component_id(analysis.import_path) for analysis in self._get_components()}
            external_packages = {
                (item.manager_id, item.package_name): item.external_package_id for item in self._external_package_analyses()
            }
            edges: list[ComponentDependencyEdge] = []
            for component in self._get_components():
                source_id = self._component_id(component.import_path)
                evidence_paths = (component.directory_rel_path, *component.go_files)
                for import_path in component.imports:
                    if import_path in local_component_ids:
                        edges.append(
                            ComponentDependencyEdge(
                                source_component_id=source_id,
                                target_id=local_component_ids[import_path],
                                target_kind='component',
                                dependency_scope='declared',
                                provenance=(
                                    derived_summary_provenance(
                                        source_kind=SourceKind.DEPENDENCY_GRAPH,
                                        source_tool='go list',
                                        evidence_summary='derived from go package import graph',
                                        evidence_paths=evidence_paths,
                                    ),
                                ),
                            )
                        )
                        continue
                    for (manager_id, external_path), external_id in external_packages.items():
                        if import_path == external_path or import_path.startswith(f'{external_path}/'):
                            edges.append(
                                ComponentDependencyEdge(
                                    source_component_id=source_id,
                                    target_id=external_id,
                                    target_kind='external_package',
                                    dependency_scope='declared',
                                    provenance=(
                                        derived_summary_provenance(
                                            source_kind=SourceKind.DEPENDENCY_GRAPH,
                                            source_tool='go list',
                                            evidence_summary='derived from go package import graph',
                                            evidence_paths=evidence_paths,
                                        ),
                                    ),
                                )
                            )
                            break
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

    def _get_tests_internal(self) -> tuple[GoTestAnalysis, ...]:
        cached = self._tests_cache
        if cached is not None:
            return cached
        with self._tests_lock:
            cached = self._tests_cache
            if cached is not None:
                return cached
            tests = tuple(
                GoTestAnalysis(
                    test_id=f'test:go:{component.import_path}',
                    name=f'go test {component.import_path}',
                    import_path=component.import_path,
                    module_root_rel_path=component.module_root_rel_path,
                    test_files=component.test_files,
                    evidence_paths=(component.directory_rel_path, *component.test_files),
                )
                for component in self._get_components()
                if component.test_files
            )
            self._tests_cache = tuple(sorted(tests, key=lambda item: item.test_id))
            return self._tests_cache

    def _external_package_analyses(self) -> tuple:
        cached = self._external_package_analysis_cache
        if cached is not None:
            return cached
        analyses = self._analysis().modules
        by_module_rel_path = {
            analysis.module_root_rel_path: analysis.package_manager.node_id
            for analysis in analyses
        }
        external_packages = []
        for module_root in self._module_roots:
            module_root_rel_path = module_root.relative_to(self.attachment_root).as_posix()
            if module_root_rel_path == ".":
                module_root_rel_path = ""
            rebased_manager_id = by_module_rel_path[self._rebase_rel_path(module_root_rel_path)]
            external_packages.extend(
                replace(
                    item,
                    external_package_id=self._external_package_id(rebased_manager_id, item.package_name),
                    manager_id=rebased_manager_id,
                    evidence_paths=self._rebase_paths(item.evidence_paths),
                )
                for item in self._analyzer.load_external_packages(
                    module_root,
                    manager_id=self._package_manager_id(module_root_rel_path),
                )
            )
        deduped = {
            (item.external_package_id, item.package_name, item.version_spec, item.manager_id): item
            for item in external_packages
        }
        self._external_package_analysis_cache = tuple(
            sorted(deduped.values(), key=lambda item: item.external_package_id)
        )
        return self._external_package_analysis_cache

    def _to_discovered_test_definition(self, test_analysis: object) -> DiscoveredTestDefinition:
        item = test_analysis
        provenance = (
            test_tool_provenance(
                source_tool='go test',
                evidence_summary='discovered from authoritative go package analysis',
                evidence_paths=item.evidence_paths,
            ),
        )
        return DiscoveredTestDefinition(
            test_definition=TestDefinition(
                id=item.test_id,
                name=item.name,
                framework=TestFramework.GO_TEST,
                test_files=item.test_files,
                provenance=provenance,
            ),
            provenance=provenance,
        )

    def _to_component(self, item: GoPackageAnalysis) -> Component:
        return Component(
            id=self._component_id(item.import_path),
            name=item.import_path,
            component_kind=item.component_kind,
            language='go',
            source_roots=item.source_roots,
            artifact_paths=item.artifact_paths,
            provenance=(
                manifest_node_provenance(
                    evidence_summary='derived from go package analysis for the module workspace',
                    evidence_paths=(item.directory_rel_path, *item.go_files),
                ),
            ),
        )

    def _to_package_manager(self, analysis: GoPackageManagerAnalysis) -> PackageManager:
        return PackageManager(
            id=analysis.node_id,
            name=analysis.display_name,
            manager=analysis.manager,
            lockfile_path=('go.sum' if 'go.sum' in analysis.owned_files else analysis.config_path),
            provenance=(
                manifest_node_provenance(
                    evidence_summary='derived from go.mod module metadata',
                    evidence_paths=analysis.owned_files,
                ),
            ),
        )

    def _to_external_package(self, item) -> ExternalPackage:
        return ExternalPackage(
            id=item.external_package_id,
            name=item.package_name,
            manager_id=item.manager_id,
            version_spec=item.version_spec,
            provenance=(
                manifest_node_provenance(
                    evidence_summary='derived from `go list -m -json all` module metadata',
                    evidence_paths=item.evidence_paths,
                ),
            ),
        )

    def _to_file_info(self, item) -> FileInfo:
        return FileInfo(
            id=f'file:{item.repository_rel_path}',
            name=Path(item.repository_rel_path).name,
            repository_rel_path=item.repository_rel_path,
            language=item.language,
            owner_id=item.owner_id,
            provenance=(
                ownership_node_provenance(
                    evidence_summary='derived from go package directory ownership',
                    evidence_paths=(item.repository_rel_path,),
                ),
            ),
        )

    def _to_entity_info(self, symbol: object) -> EntityInfo:
        return self._symbol_translator.to_entity_info(symbol)

    def _to_code_location(
        self,
        location: tuple[str, int, int, int, int],
        *,
        operation: str,
    ) -> CodeLocation:
        return self._location_translator.to_code_location(location, operation=operation)

    @staticmethod
    def _component_id(import_path: str) -> str:
        return f'component:go:{import_path}'

    def _rebase_workspace_analysis(self, analysis):
        modules = tuple(self._rebase_module(item) for item in analysis.modules)
        return replace(
            analysis,
            module_roots_rel_path=tuple(item.module_root_rel_path for item in modules),
            modules=modules,
            components=tuple(item for module in modules for item in module.components),
            package_managers=tuple(module.package_manager for module in modules),
            external_packages=tuple(item for module in modules for item in module.external_packages),
            files=tuple(sorted({item.repository_rel_path: item for module in modules for item in module.files}.values(), key=lambda item: item.repository_rel_path)),
        )

    def _rebase_module(self, analysis):
        rebased_rel_path = self._rebase_rel_path(analysis.module_root_rel_path)
        rebased_manager_id = self._package_manager_id(rebased_rel_path)
        components = tuple(self._rebase_component(item, rebased_rel_path) for item in analysis.components)
        package_manager = replace(
            analysis.package_manager,
            node_id=rebased_manager_id,
            module_root_rel_path=rebased_rel_path,
            config_path=self._rebase_optional_path(analysis.package_manager.config_path),
            owned_files=self._rebase_paths(analysis.package_manager.owned_files),
        )
        external_packages = tuple(
            replace(
                item,
                external_package_id=self._external_package_id(rebased_manager_id, item.package_name),
                manager_id=rebased_manager_id,
                evidence_paths=self._rebase_paths(item.evidence_paths),
            )
            for item in analysis.external_packages
        )
        files = tuple(
            replace(
                item,
                repository_rel_path=self._rebase_rel_path(item.repository_rel_path),
                owner_id=(
                    rebased_manager_id
                    if item.owner_id == analysis.package_manager.node_id
                    else item.owner_id
                ),
            )
            for item in analysis.files
        )
        return replace(
            analysis,
            module_root_rel_path=rebased_rel_path,
            components=components,
            package_manager=package_manager,
            external_packages=external_packages,
            files=files,
        )

    def _rebase_component(self, analysis: GoPackageAnalysis, rebased_module_root_rel_path: str) -> GoPackageAnalysis:
        return replace(
            analysis,
            module_root_rel_path=rebased_module_root_rel_path,
            directory_rel_path=self._rebase_rel_path(analysis.directory_rel_path),
            source_roots=self._rebase_paths(analysis.source_roots),
            artifact_paths=self._rebase_paths(analysis.artifact_paths),
            go_files=self._rebase_paths(analysis.go_files),
            test_files=self._rebase_paths(analysis.test_files),
        )

    def _rebase_paths(self, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self._rebase_rel_path(item) for item in values)

    def _rebase_optional_path(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self._rebase_rel_path(value)

    def _rebase_rel_path(self, value: str) -> str:
        normalized = value.replace("\\", "/").strip().removeprefix("./")
        attachment_root_rel_path = self.attachment_root_rel_path.strip().removesuffix("/")
        if not attachment_root_rel_path or attachment_root_rel_path == ".":
            return normalized
        if not normalized:
            return attachment_root_rel_path
        return f"{attachment_root_rel_path}/{normalized}"

    @staticmethod
    def _package_manager_id(module_root_rel_path: str) -> str:
        return "pkgmgr:go:root" if not module_root_rel_path else f"pkgmgr:go:{module_root_rel_path}"

    @staticmethod
    def _external_package_id(manager_id: str, package_name: str) -> str:
        normalized_manager = manager_id.replace(":", "/")
        return f"pkgext:go:{normalized_manager}:{package_name}"

    def _test_id_for_component(self, component_id: str) -> str:
        component = self.repository.resolve_owner(component_id)
        return f'test:go:{component.name}'

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
                    evidence_summary=summary if reason is None else f'{summary}: {reason}',
                    evidence_paths=tuple(),
                ),
            ),
        )
