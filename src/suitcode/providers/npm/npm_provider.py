from __future__ import annotations

from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.action_models import ActionKind, ActionQuery, RepositoryAction
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.models import (
    Aggregator,
    Component,
    EntityInfo,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition,
)
from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget, TestExecutionResult, TestTargetDescription
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
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.npm.symbol_service import NpmFileSymbolService, NpmSymbolService
from suitcode.providers.npm.symbol_translation import NpmSymbolTranslator
from suitcode.providers.npm.translation import NpmModelTranslator
from suitcode.providers.npm.workspace_analyzer import NpmWorkspaceAnalyzer
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.shared.code_facade import CodeFacadeMixin
from suitcode.providers.shared.component_index import ComponentIndexBuilder
from suitcode.providers.shared.actions import ProviderActionSpec, ProviderActionTranslator
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader
from suitcode.providers.shared.package_json.models import PackageJsonWorkspace
from suitcode.providers.shared.test_facade import TestFacadeMixin
from suitcode.providers.shared.test_execution import TestExecutionService

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class NPMProvider(
    CodeFacadeMixin,
    TestFacadeMixin,
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
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        root = repository_root.expanduser().resolve()
        manifest_path = root / "package.json"
        if not manifest_path.exists():
            return frozenset()

        loader = PackageJsonWorkspaceLoader()
        loader.load(root)
        return frozenset(
            {
                ProviderRole.ARCHITECTURE,
                ProviderRole.CODE,
                ProviderRole.TEST,
                ProviderRole.QUALITY,
            }
        )

    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)
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
        self._quality_service: NpmQualityService | None = None
        self._test_execution_service: TestExecutionService | None = None

    def get_components(self) -> tuple[Component, ...]:
        return tuple(sorted((self._translator.to_component(item) for item in self._get_components()), key=lambda item: item.id))

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return tuple(sorted((self._translator.to_aggregator(item) for item in self._get_aggregators()), key=lambda item: item.id))

    def get_runners(self) -> tuple[Runner, ...]:
        return tuple(sorted((self._translator.to_runner(item) for item in self._get_runners()), key=lambda item: item.id))

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return tuple(sorted((self._translator.to_package_manager(item) for item in self._get_package_managers()), key=lambda item: item.id))

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return tuple(sorted((self._translator.to_external_package(item) for item in self._get_external_packages()), key=lambda item: item.id))

    def get_files(self) -> tuple[FileInfo, ...]:
        return tuple(sorted((self._translator.to_file_info(item) for item in self._get_files()), key=lambda item: item.id))

    def get_component_dependency_edges(self, component_id: str | None = None) -> tuple[ComponentDependencyEdge, ...]:
        edges = self._all_component_dependency_edges()
        if component_id is None:
            return edges
        component_index = self._component_analysis_by_id()
        if component_id not in component_index:
            raise ValueError(f"unknown component id: `{component_id}`")
        return tuple(item for item in edges if item.source_component_id == component_id)

    def get_actions(self) -> tuple[RepositoryAction, ...]:
        return tuple(
            sorted(
                (self._action_translator.to_repository_action(item) for item in self._get_actions()),
                key=lambda item: item.id,
            )
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
                raise ValueError(f"component owner id could not be resolved to a package: `{owner.id}`")
            return self._tests_for_package_root(package_root, matched_owner_id=owner.id)

        assert target.repository_rel_path is not None
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
            raise ValueError(f"file could not be resolved to a workspace package: `{target.repository_rel_path}`")
        return self._tests_for_package_root(package_root, matched_owner_id=owner_info.owner.id, matched_repository_rel_path=target.repository_rel_path)

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._lint_file(repository_rel_path, is_fix))

    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._format_file(repository_rel_path))

    def describe_test_target(self, test_id: str) -> TestTargetDescription:
        discovered = self._discovered_test_by_id(test_id)
        action = self._test_action_for_id(test_id)
        warning = None
        if not discovered.is_authoritative:
            warning = (
                "Test target scope is heuristic; command is deterministic but may include tests beyond exact ownership."
            )
        return TestTargetDescription(
            test_definition=discovered.test_definition,
            command_argv=action.invocation.argv,
            command_cwd=action.invocation.cwd,
            is_authoritative=discovered.is_authoritative,
            warning=warning,
            provenance=(*discovered.provenance, *action.provenance),
        )

    def run_test_targets(self, test_ids: tuple[str, ...], timeout_seconds: int) -> tuple[TestExecutionResult, ...]:
        self._validate_test_id_batch(test_ids)
        if timeout_seconds < 1 or timeout_seconds > 3600:
            raise ValueError("timeout_seconds must be between 1 and 3600")
        execution_service = self._build_test_execution_service()
        return tuple(
            execution_service.run_target(self.describe_test_target(test_id), timeout_seconds=timeout_seconds)
            for test_id in test_ids
        )

    def _load_workspace(self) -> PackageJsonWorkspace:
        if self._workspace is None:
            self._workspace = self._workspace_loader.load(self.repository.root)
        return self._workspace

    def _build_analyzer(self) -> NpmWorkspaceAnalyzer:
        if self._analyzer is None:
            self._analyzer = NpmWorkspaceAnalyzer(self._load_workspace())
        return self._analyzer

    def _get_components(self) -> tuple[NpmPackageAnalysis, ...]:
        return self._build_analyzer().analyze_components()

    def _get_aggregators(self) -> tuple[NpmAggregatorAnalysis, ...]:
        return self._build_analyzer().analyze_aggregators()

    def _get_runners(self) -> tuple[NpmRunnerAnalysis, ...]:
        return self._build_analyzer().analyze_runners()

    def _get_tests(self) -> tuple[NpmTestAnalysis, ...]:
        return self._build_analyzer().analyze_tests()

    def _get_package_managers(self) -> tuple[NpmPackageManagerAnalysis, ...]:
        return self._build_analyzer().analyze_package_managers()

    def _get_external_packages(self) -> tuple[NpmExternalPackageAnalysis, ...]:
        return self._build_analyzer().analyze_external_packages()

    def _get_files(self) -> tuple[NpmOwnedFileAnalysis, ...]:
        return self._build_analyzer().analyze_files()

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
            package_root = package.repository_rel_path
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
                test_file.startswith(f"{package_root}/") or test_file == package_root
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

    def _discovered_test_by_id(self, test_id: str):
        for discovered in self.get_discovered_tests():
            if discovered.test_definition.id == test_id:
                return discovered
        raise ValueError(f"unknown npm test id: `{test_id}`")

    def _test_action_for_id(self, test_id: str):
        actions = tuple(
            action
            for action in self.repository.list_actions(ActionQuery(test_id=test_id))
            if action.provider_id == self.PROVIDER_ID and action.kind == ActionKind.TEST_EXECUTION
        )
        if not actions:
            raise ValueError(f"missing npm test action for test id `{test_id}`")
        if len(actions) != 1:
            raise ValueError(f"ambiguous npm test actions for test id `{test_id}`")
        return actions[0]

    @staticmethod
    def _validate_test_id_batch(test_ids: tuple[str, ...]) -> None:
        if not test_ids:
            raise ValueError("test_ids must not be empty")
        if len(test_ids) > 25:
            raise ValueError("test_ids must not contain more than 25 items")
        if any(not test_id.strip() for test_id in test_ids):
            raise ValueError("test_ids must not contain empty values")
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("test_ids must not contain duplicates")
