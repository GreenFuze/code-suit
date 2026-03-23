from __future__ import annotations

import shutil
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.models import Aggregator, Component, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition, TestFramework
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
from suitcode.providers.go.action_service import GoActionService
from suitcode.providers.go.models import GoPackageAnalysis, GoPackageManagerAnalysis, GoTestAnalysis
from suitcode.providers.go.workspace_analyzer import GoWorkspaceAnalyzer
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import (
    ActionRuntimeCapabilities,
    RuntimeCapability,
    RuntimeCapabilityAvailability,
    TestRuntimeCapabilities,
)
from suitcode.providers.shared.actions import ProviderActionSpec, ProviderActionTranslator
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
    TestFacadeMixin,
    DeterministicTestTargetMixin,
    ArchitectureProviderBase,
    TestProviderBase,
    ActionProviderBase,
):
    PROVIDER_ID = 'go'
    DISPLAY_NAME = 'go'
    BUILD_SYSTEMS = ('go',)
    PROGRAMMING_LANGUAGES = ('go',)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        if GoWorkspaceAnalyzer.detect_supported_workspace(repository_root):
            return frozenset({ProviderRole.ARCHITECTURE, ProviderRole.TEST})
        return frozenset()

    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)
        self._module_roots = GoWorkspaceAnalyzer.discover_module_roots(repository.root)
        if not self._module_roots:
            raise ValueError(f'go provider requires one or more go.mod files and no go.work under `{repository.root}`')
        self._analyzer = GoWorkspaceAnalyzer(repository.root)
        self._action_service = GoActionService()
        self._action_translator = ProviderActionTranslator(provider_id='go', default_test_tool='go test')
        self._component_id_index: dict[str, GoPackageAnalysis] | None = None
        self._dependency_edges_cache: tuple[ComponentDependencyEdge, ...] | None = None
        self._test_execution_service: TestExecutionService | None = None
        self._tests_cache: tuple[GoTestAnalysis, ...] | None = None
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
        return self._translate_sorted(self._analysis().external_packages, self._to_external_package, key=lambda item: item.id)

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
        return self._analyzer.analyze()

    def _build_test_execution_service(self) -> TestExecutionService:
        if self._test_execution_service is None:
            self._test_execution_service = TestExecutionService(repository_root=self.repository.root, suit_dir=self.repository.suit_dir)
        return self._test_execution_service

    def _get_components(self) -> tuple[GoPackageAnalysis, ...]:
        return self._analysis().components

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
                (item.manager_id, item.package_name): item.external_package_id for item in self._analysis().external_packages
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

    @staticmethod
    def _component_id(import_path: str) -> str:
        return f'component:go:{import_path}'

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
