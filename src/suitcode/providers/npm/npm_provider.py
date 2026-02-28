from __future__ import annotations

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition,
)
from suitcode.core.repository import Repository
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmExternalPackageAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)
from suitcode.providers.npm.translation import NpmModelTranslator
from suitcode.providers.npm.workspace_analyzer import NpmWorkspaceAnalyzer
from suitcode.providers.shared.package_json import PackageJsonWorkspaceLoader
from suitcode.providers.shared.package_json.models import PackageJsonWorkspace


class NPMProvider(ArchitectureProviderBase):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)
        self._workspace_loader = PackageJsonWorkspaceLoader()
        self._translator = NpmModelTranslator()
        self._workspace: PackageJsonWorkspace | None = None
        self._analyzer: NpmWorkspaceAnalyzer | None = None

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
