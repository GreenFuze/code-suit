from __future__ import annotations

from suitcode.core.code.models import CodeLocation
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
from suitcode.core.tests.models import RelatedTestMatch, RelatedTestTarget
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
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
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.npm.symbol_service import NpmFileSymbolService, NpmSymbolService
from suitcode.providers.npm.symbol_translation import NpmSymbolTranslator
from suitcode.providers.npm.translation import NpmModelTranslator
from suitcode.providers.npm.workspace_analyzer import NpmWorkspaceAnalyzer
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader
from suitcode.providers.shared.package_json.models import PackageJsonWorkspace

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class NPMProvider(ArchitectureProviderBase, CodeProviderBase, TestProviderBase, QualityProviderBase):
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
        self._symbol_translator = NpmSymbolTranslator()
        self._quality_translator = NpmQualityTranslator(self._symbol_translator)
        self._workspace: PackageJsonWorkspace | None = None
        self._analyzer: NpmWorkspaceAnalyzer | None = None
        self._symbol_service: NpmSymbolService | None = None
        self._file_symbol_service: NpmFileSymbolService | None = None
        self._quality_service: NpmQualityService | None = None

    def get_components(self) -> tuple[Component, ...]:
        return tuple(sorted((self._translator.to_component(item) for item in self._get_components()), key=lambda item: item.id))

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return tuple(sorted((self._translator.to_aggregator(item) for item in self._get_aggregators()), key=lambda item: item.id))

    def get_runners(self) -> tuple[Runner, ...]:
        return tuple(sorted((self._translator.to_runner(item) for item in self._get_runners()), key=lambda item: item.id))

    def get_tests(self) -> tuple[TestDefinition, ...]:
        return tuple(sorted((self._translator.to_test_definition(item) for item in self._get_tests()), key=lambda item: item.id))

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return tuple(sorted((self._translator.to_package_manager(item) for item in self._get_package_managers()), key=lambda item: item.id))

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return tuple(sorted((self._translator.to_external_package(item) for item in self._get_external_packages()), key=lambda item: item.id))

    def get_files(self) -> tuple[FileInfo, ...]:
        return tuple(sorted((self._translator.to_file_info(item) for item in self._get_files()), key=lambda item: item.id))

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

    def get_related_tests(self, target: RelatedTestTarget) -> tuple[RelatedTestMatch, ...]:
        tests = self.get_tests()
        if target.owner_id is not None:
            owner = self.repository.resolve_owner(target.owner_id)
            if owner.kind == "test_definition":
                matches = [test_definition for test_definition in tests if test_definition.id == target.owner_id]
                if not matches:
                    raise ValueError(f"test owner id could not be resolved: `{target.owner_id}`")
                return (
                    RelatedTestMatch(
                        test_definition=matches[0],
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
            matches = [test_definition for test_definition in tests if target.repository_rel_path in test_definition.test_files]
            if not matches:
                raise ValueError(f"test-owned file could not be resolved to a test definition: `{target.repository_rel_path}`")
            return tuple(
                RelatedTestMatch(
                    test_definition=test_definition,
                    relation_reason="same_owner",
                    matched_owner_id=test_definition.id,
                    matched_repository_rel_path=target.repository_rel_path,
                )
                for test_definition in matches
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
        matches = [
            test_definition
            for test_definition in self.get_tests()
            if any(test_file.startswith(f"{package_root}/") or test_file == package_root for test_file in test_definition.test_files)
        ]
        return tuple(
            RelatedTestMatch(
                test_definition=test_definition,
                relation_reason="same_package",
                matched_owner_id=matched_owner_id,
                matched_repository_rel_path=matched_repository_rel_path,
            )
            for test_definition in matches
        )
