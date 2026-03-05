from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.action_models import ActionKind, ActionQuery, RepositoryAction
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.models import Aggregator, Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget, TestExecutionResult, TestTargetDescription
from suitcode.core.provenance_builders import manifest_provenance
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.python.action_service import PythonActionService
from suitcode.providers.python.models import (
    PythonExternalPackageAnalysis,
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
)
from suitcode.providers.python.location_translation import PythonLocationTranslator
from suitcode.providers.python.quality_service import PythonQualityService
from suitcode.providers.python.quality_translation import PythonQualityTranslator
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol
from suitcode.providers.python.symbol_service import PythonFileSymbolService, PythonSymbolService
from suitcode.providers.python.symbol_translation import PythonSymbolTranslator
from suitcode.providers.python.test_discovery import PythonTestDiscoverer
from suitcode.providers.python.test_models import PythonTestAnalysis
from suitcode.providers.python.test_translation import PythonTestTranslator
from suitcode.providers.python.translation import PythonModelTranslator
from suitcode.providers.python.workspace_analyzer import PythonWorkspaceAnalyzer
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.shared.actions import ProviderActionSpec, ProviderActionTranslator
from suitcode.providers.shared.code_facade import CodeFacadeMixin
from suitcode.providers.shared.component_index import ComponentIndexBuilder
from suitcode.providers.shared.pyproject import PyProjectManifest, PyProjectWorkspaceLoader
from suitcode.providers.shared.test_facade import TestFacadeMixin
from suitcode.providers.shared.test_execution import TestExecutionService
from suitcode.providers.test_provider_base import TestProviderBase

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class PythonProvider(
    CodeFacadeMixin,
    TestFacadeMixin,
    ArchitectureProviderBase,
    CodeProviderBase,
    TestProviderBase,
    QualityProviderBase,
    ActionProviderBase,
):
    PROVIDER_ID = 'python'
    DISPLAY_NAME = 'python'
    BUILD_SYSTEMS = ('pip',)
    PROGRAMMING_LANGUAGES = ('python',)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        root = repository_root.expanduser().resolve()
        manifest_path = root / 'pyproject.toml'
        if not manifest_path.exists():
            return frozenset()

        manifest = PyProjectWorkspaceLoader().load(root)
        if manifest.project is None and manifest.build_system is None:
            return frozenset()
        return frozenset({ProviderRole.ARCHITECTURE, ProviderRole.CODE, ProviderRole.TEST, ProviderRole.QUALITY})

    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)
        self._manifest_loader = PyProjectWorkspaceLoader()
        self._translator = PythonModelTranslator()
        self._action_service = PythonActionService()
        self._action_translator = ProviderActionTranslator(provider_id="python", default_test_tool="pytest")
        self._symbol_translator = PythonSymbolTranslator()
        self._location_translator = PythonLocationTranslator()
        self._test_translator = PythonTestTranslator()
        self._quality_translator = PythonQualityTranslator(self._symbol_translator)
        self._manifest: PyProjectManifest | None = None
        self._analyzer: PythonWorkspaceAnalyzer | None = None
        self._component_id_index: dict[str, PythonPackageComponentAnalysis] | None = None
        self._dependency_edges_cache: tuple[ComponentDependencyEdge, ...] | None = None
        self._symbol_service: PythonSymbolService | None = None
        self._file_symbol_service: PythonFileSymbolService | None = None
        self._test_discoverer: PythonTestDiscoverer | None = None
        self._quality_service: PythonQualityService | None = None
        self._test_execution_service: TestExecutionService | None = None

    def get_components(self) -> tuple[Component, ...]:
        return tuple(sorted((self._translator.to_component(item) for item in self._get_components()), key=lambda item: item.id))

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return tuple()

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

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        discovered_tests = self.get_discovered_tests()
        if not discovered_tests:
            return tuple()
        if target.owner_id is not None:
            owner = self.repository.resolve_owner(target.owner_id)
            if owner.kind not in {"component", "test_definition"}:
                return tuple()
            if owner.kind == "test_definition":
                matches = [item for item in discovered_tests if item.test_definition.id == target.owner_id]
                if not matches:
                    raise ValueError(f"test owner id could not be resolved: `{target.owner_id}`")
                return tuple(
                    RelatedTestMatch(
                        test_definition=matches[0].test_definition,
                        relation_reason="same_owner",
                        matched_owner_id=target.owner_id,
                    )
                    for _ in [0]
                )
            return tuple(
                RelatedTestMatch(
                    test_definition=discovered_test.test_definition,
                    relation_reason="same_component",
                    matched_owner_id=target.owner_id,
                )
                for discovered_test in discovered_tests
            )

        assert target.repository_rel_path is not None
        owner_info = self.repository.get_file_owner(target.repository_rel_path)
        if owner_info.owner.kind != "component":
            return tuple()
        return tuple(
            RelatedTestMatch(
                test_definition=discovered_test.test_definition,
                relation_reason="same_component",
                matched_owner_id=owner_info.owner.id,
                matched_repository_rel_path=target.repository_rel_path,
            )
            for discovered_test in discovered_tests
        )

    def get_actions(self) -> tuple[RepositoryAction, ...]:
        return tuple(
            sorted(
                (self._action_translator.to_repository_action(item) for item in self._get_actions()),
                key=lambda item: item.id,
            )
        )

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._build_quality_service().lint_file(repository_rel_path, is_fix))

    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._build_quality_service().format_file(repository_rel_path))

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

    def _load_manifest(self) -> PyProjectManifest:
        if self._manifest is None:
            self._manifest = self._manifest_loader.load(self.repository.root)
        return self._manifest

    def _build_analyzer(self) -> PythonWorkspaceAnalyzer:
        if self._analyzer is None:
            self._analyzer = PythonWorkspaceAnalyzer(self.repository.root, self._load_manifest())
        return self._analyzer

    def _build_symbol_service(self) -> PythonSymbolService:
        if self._symbol_service is None:
            self._symbol_service = PythonSymbolService(self.repository)
        return self._symbol_service

    def _build_file_symbol_service(self) -> PythonFileSymbolService:
        if self._file_symbol_service is None:
            self._file_symbol_service = PythonFileSymbolService(self.repository)
        return self._file_symbol_service

    def _build_test_discoverer(self) -> PythonTestDiscoverer:
        if self._test_discoverer is None:
            self._test_discoverer = PythonTestDiscoverer(self.repository.root, self._load_manifest())
        return self._test_discoverer

    def _build_quality_service(self) -> PythonQualityService:
        if self._quality_service is None:
            self._quality_service = PythonQualityService(self.repository)
        return self._quality_service

    def _build_test_execution_service(self) -> TestExecutionService:
        if self._test_execution_service is None:
            self._test_execution_service = TestExecutionService(
                repository_root=self.repository.root,
                suit_dir=self.repository.suit_dir,
            )
        return self._test_execution_service

    def _get_components(self) -> tuple[PythonPackageComponentAnalysis, ...]:
        return self._build_analyzer().analyze_components()

    def _component_analysis_by_id(self) -> dict[str, PythonPackageComponentAnalysis]:
        if self._component_id_index is None:
            self._component_id_index = {
                key: value
                for key, value in ComponentIndexBuilder.build(
                    self._get_components(),
                    lambda analysis: self._translator.to_component(analysis).id,
                    lambda component_id: f"duplicate python component id detected: `{component_id}`",
                ).items()
            }
        return self._component_id_index

    def _all_component_dependency_edges(self) -> tuple[ComponentDependencyEdge, ...]:
        if self._dependency_edges_cache is None:
            external_packages = self._get_external_packages()
            edges: list[ComponentDependencyEdge] = []
            for source_component_id in sorted(self._component_analysis_by_id()):
                for package in external_packages:
                    edges.append(
                        ComponentDependencyEdge(
                            source_component_id=source_component_id,
                            target_id=self._translator.to_external_package(package).id,
                            target_kind="external_package",
                            dependency_scope="declared",
                            provenance=(
                                manifest_provenance(
                                    evidence_summary="derived from pyproject.toml project dependency metadata",
                                    evidence_paths=("pyproject.toml",),
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

    def _get_runners(self) -> tuple[PythonRunnerAnalysis, ...]:
        return self._build_analyzer().analyze_runners()

    def _get_package_managers(self) -> tuple[PythonPackageManagerAnalysis, ...]:
        return self._build_analyzer().analyze_package_managers()

    def _get_external_packages(self) -> tuple[PythonExternalPackageAnalysis, ...]:
        return self._build_analyzer().analyze_external_packages()

    def _get_files(self) -> tuple[PythonOwnedFileAnalysis, ...]:
        return self._build_analyzer().analyze_files()

    def _get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[PythonWorkspaceSymbol, ...]:
        return self._build_symbol_service().get_symbols(query, is_case_sensitive=is_case_sensitive)

    def _list_file_symbols(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[PythonWorkspaceSymbol, ...]:
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

    def _get_tests_internal(self) -> tuple[PythonTestAnalysis, ...]:
        return self._build_test_discoverer().discover()

    def _to_discovered_test_definition(self, test_analysis: object):
        return self._test_translator.to_discovered_test_definition(test_analysis)

    def _get_actions(self) -> tuple[ProviderActionSpec, ...]:
        return self._action_service.discover(
            components=self._get_components(),
            runners=self._get_runners(),
            tests=self._get_tests_internal(),
            has_build_system=self._load_manifest().build_system is not None,
        )

    def _discovered_test_by_id(self, test_id: str):
        for discovered in self.get_discovered_tests():
            if discovered.test_definition.id == test_id:
                return discovered
        raise ValueError(f"unknown python test id: `{test_id}`")

    def _test_action_for_id(self, test_id: str):
        actions = tuple(
            action
            for action in self.repository.list_actions(ActionQuery(test_id=test_id))
            if action.provider_id == self.PROVIDER_ID and action.kind == ActionKind.TEST_EXECUTION
        )
        if not actions:
            raise ValueError(f"missing python test action for test id `{test_id}`")
        if len(actions) != 1:
            raise ValueError(f"ambiguous python test actions for test id `{test_id}`")
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
