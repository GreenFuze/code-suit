from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import DependencyRef
from suitcode.core.models import Aggregator, Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, RelatedTestTarget
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.python.models import (
    PythonExternalPackageAnalysis,
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
)
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
from suitcode.providers.shared.pyproject import PyProjectManifest, PyProjectWorkspaceLoader
from suitcode.providers.test_provider_base import TestProviderBase

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class PythonProvider(ArchitectureProviderBase, CodeProviderBase, TestProviderBase, QualityProviderBase):
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
        self._symbol_translator = PythonSymbolTranslator()
        self._test_translator = PythonTestTranslator()
        self._quality_translator = PythonQualityTranslator(self._symbol_translator)
        self._manifest: PyProjectManifest | None = None
        self._analyzer: PythonWorkspaceAnalyzer | None = None
        self._component_id_index: dict[str, PythonPackageComponentAnalysis] | None = None
        self._symbol_service: PythonSymbolService | None = None
        self._file_symbol_service: PythonFileSymbolService | None = None
        self._test_discoverer: PythonTestDiscoverer | None = None
        self._quality_service: PythonQualityService | None = None

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

    def get_component_dependencies(self, component_id: str) -> tuple[DependencyRef, ...]:
        if component_id not in self._component_analysis_by_id():
            return tuple()
        return tuple(
            sorted(
                (
                    DependencyRef(
                        target_id=self._translator.to_external_package(item).id,
                        target_kind="external_package",
                        dependency_scope="declared",
                    )
                    for item in self._get_external_packages()
                ),
                key=lambda item: (item.target_kind, item.target_id, item.dependency_scope),
            )
        )

    def get_component_dependents(self, component_id: str) -> tuple[str, ...]:
        if component_id not in self._component_analysis_by_id():
            return tuple()
        return tuple()

    def get_symbol(self, query: str, is_case_sensitive: bool = False) -> tuple[EntityInfo, ...]:
        return tuple(
            sorted(
                (self._symbol_translator.to_entity_info(item) for item in self._get_symbols(query, is_case_sensitive=is_case_sensitive)),
                key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def list_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        return tuple(
            sorted(
                (
                    self._symbol_translator.to_entity_info(item)
                    for item in self._build_file_symbol_service().list_file_symbols(
                        repository_rel_path,
                        query=query,
                        is_case_sensitive=is_case_sensitive,
                    )
                ),
                key=lambda item: (item.name, item.entity_kind, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[CodeLocation, ...]:
        return tuple(
            CodeLocation(
                repository_rel_path=path,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
            )
            for path, line_start, line_end, column_start, column_end in self._build_file_symbol_service().find_definition(
                repository_rel_path,
                line,
                column,
            )
        )

    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        return tuple(
            CodeLocation(
                repository_rel_path=path,
                line_start=line_start,
                line_end=line_end,
                column_start=column_start,
                column_end=column_end,
            )
            for path, line_start, line_end, column_start, column_end in self._build_file_symbol_service().find_references(
                repository_rel_path,
                line,
                column,
                include_definition=include_definition,
            )
        )

    def get_tests(self) -> tuple[TestDefinition, ...]:
        return tuple(item.test_definition for item in self.get_discovered_tests())

    def get_discovered_tests(self) -> tuple[DiscoveredTestDefinition, ...]:
        return tuple(
            sorted(
                (self._test_translator.to_discovered_test_definition(item) for item in self._get_tests()),
                key=lambda item: item.test_definition.id,
            )
        )

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        discovered_tests = self.get_discovered_tests()
        tests = tuple(item.test_definition for item in discovered_tests)
        if not tests:
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
                        discovery_method=matches[0].discovery_method,
                        discovery_tool=matches[0].discovery_tool,
                        is_authoritative=matches[0].is_authoritative,
                    )
                    for _ in [0]
                )
            return tuple(
                RelatedTestMatch(
                    test_definition=discovered_test.test_definition,
                    relation_reason="same_component",
                    matched_owner_id=target.owner_id,
                    discovery_method=discovered_test.discovery_method,
                    discovery_tool=discovered_test.discovery_tool,
                    is_authoritative=discovered_test.is_authoritative,
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
                discovery_method=discovered_test.discovery_method,
                discovery_tool=discovered_test.discovery_tool,
                is_authoritative=discovered_test.is_authoritative,
            )
            for discovered_test in discovered_tests
        )

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._build_quality_service().lint_file(repository_rel_path, is_fix))

    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        return self._quality_translator.to_quality_file_result(self._build_quality_service().format_file(repository_rel_path))

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

    def _get_components(self) -> tuple[PythonPackageComponentAnalysis, ...]:
        return self._build_analyzer().analyze_components()

    def _component_analysis_by_id(self) -> dict[str, PythonPackageComponentAnalysis]:
        if self._component_id_index is None:
            self._component_id_index = {}
            for analysis in self._get_components():
                translated = self._translator.to_component(analysis)
                if translated.id in self._component_id_index:
                    raise ValueError(f"duplicate python component id detected: `{translated.id}`")
                self._component_id_index[translated.id] = analysis
        return self._component_id_index

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

    def _get_tests(self) -> tuple[PythonTestAnalysis, ...]:
        return self._build_test_discoverer().discover()
