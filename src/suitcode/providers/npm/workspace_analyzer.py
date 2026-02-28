from __future__ import annotations

from pathlib import Path

from suitcode.core.models import ProgrammingLanguage
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.providers.npm.classifier import NpmPackageClassifier
from suitcode.providers.npm.file_inventory import OwnedFileInventoryBuilder
from suitcode.providers.npm.language_inference import NpmLanguageInferer
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmExternalPackageAnalysis,
    NpmPackageAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
    NpmWorkspaceModel,
)
from suitcode.providers.npm.package_manager_discovery import RepositoryPackageManagerDiscoverer
from suitcode.providers.npm.runner_parser import NpmRunnerScriptInspector
from suitcode.providers.npm.test_discovery import NpmTestDiscoverer
from suitcode.providers.shared.package_json.models import PackageJsonManifest, PackageJsonWorkspace, PackageJsonWorkspacePackage


class NpmWorkspaceAnalyzer:
    _SOURCE_DIR_CANDIDATES = ("src", "lib", "app")
    _ARTIFACT_DIR_CANDIDATES = ("dist", "build", "lib")

    def __init__(self, workspace: PackageJsonWorkspace) -> None:
        self._workspace = workspace
        self._workspace_model = NpmWorkspaceModel(
            packages=workspace.packages,
            root_manifest=workspace.root_manifest,
            workspace_package_names=frozenset(workspace.package_names()),
        )
        self._runner_inspector = NpmRunnerScriptInspector()
        self._classifier = NpmPackageClassifier(self._runner_inspector)
        self._language_inferer = NpmLanguageInferer()
        self._test_discoverer = NpmTestDiscoverer()
        self._package_manager_discoverer = RepositoryPackageManagerDiscoverer()
        self._file_inventory_builder = OwnedFileInventoryBuilder()
        self._components_cache: tuple[NpmPackageAnalysis, ...] | None = None
        self._aggregators_cache: tuple[NpmAggregatorAnalysis, ...] | None = None
        self._runners_cache: tuple[NpmRunnerAnalysis, ...] | None = None
        self._tests_cache: tuple[NpmTestAnalysis, ...] | None = None
        self._package_managers_cache: tuple[NpmPackageManagerAnalysis, ...] | None = None
        self._external_packages_cache: tuple[NpmExternalPackageAnalysis, ...] | None = None
        self._files_cache: tuple[NpmOwnedFileAnalysis, ...] | None = None

    def analyze_components(self) -> tuple[NpmPackageAnalysis, ...]:
        if self._components_cache is None:
            analyses: list[NpmPackageAnalysis] = []
            for package in self._workspace_model.packages:
                if self._classifier.classify(package) != "component":
                    continue
                analyses.append(self._build_package_analysis(package))
            self._components_cache = tuple(sorted(analyses, key=lambda analysis: analysis.package_name))
        return self._components_cache

    def analyze_aggregators(self) -> tuple[NpmAggregatorAnalysis, ...]:
        if self._aggregators_cache is None:
            analyses = []
            for package in self._workspace_model.packages:
                if self._classifier.classify(package) != "aggregator":
                    continue
                package_name = self._package_name(package)
                analyses.append(
                    NpmAggregatorAnalysis(
                        package_name=package_name,
                        package_path=package.repository_rel_path,
                        manifest_path=package.package_json_rel_path,
                    )
                )
            self._aggregators_cache = tuple(sorted(analyses, key=lambda analysis: analysis.package_name))
        return self._aggregators_cache

    def analyze_runners(self) -> tuple[NpmRunnerAnalysis, ...]:
        if self._runners_cache is None:
            analyses: list[NpmRunnerAnalysis] = []
            for package in self._workspace_model.packages:
                analyses.extend(self._runner_inspector.inspect(package))
            self._runners_cache = tuple(sorted(analyses, key=lambda analysis: (analysis.package_name, analysis.script_name)))
        return self._runners_cache

    def analyze_tests(self) -> tuple[NpmTestAnalysis, ...]:
        if self._tests_cache is None:
            analyses = []
            for package in self._workspace_model.packages:
                analysis = self._test_discoverer.discover(package)
                if analysis is not None:
                    analyses.append(analysis)
            self._tests_cache = tuple(sorted(analyses, key=lambda analysis: analysis.package_name))
        return self._tests_cache

    def analyze_package_managers(self) -> tuple[NpmPackageManagerAnalysis, ...]:
        if self._package_managers_cache is None:
            self._package_managers_cache = self._package_manager_discoverer.discover(self._workspace.repository_root)
        return self._package_managers_cache

    def analyze_external_packages(self) -> tuple[NpmExternalPackageAnalysis, ...]:
        if self._external_packages_cache is None:
            external_packages: dict[str, str] = {}
            for manifest in [self._workspace.root_manifest, *(package.manifest for package in self._workspace_model.packages)]:
                for dependency_name in manifest.dependencies.all_dependency_names():
                    if dependency_name in self._workspace_model.workspace_package_names:
                        continue
                    version_spec = manifest.dependencies.version_for(dependency_name)
                    if version_spec is None:
                        raise ValueError(f"missing version spec for dependency {dependency_name}")
                    external_packages.setdefault(dependency_name, version_spec)
            analyses = [
                NpmExternalPackageAnalysis(
                    package_name=name,
                    version_spec=external_packages[name],
                    manager_id="pkgmgr:npm:root",
                )
                for name in sorted(external_packages)
            ]
            self._external_packages_cache = tuple(analyses)
        return self._external_packages_cache

    def analyze_files(self) -> tuple[NpmOwnedFileAnalysis, ...]:
        if self._files_cache is None:
            self._files_cache = self._file_inventory_builder.build(
                repository_root=self._workspace.repository_root,
                components=self.analyze_components(),
                aggregators=self.analyze_aggregators(),
                runners=self.analyze_runners(),
                tests=self.analyze_tests(),
                package_managers=self.analyze_package_managers(),
            )
        return self._files_cache

    def _build_package_analysis(self, package: PackageJsonWorkspacePackage) -> NpmPackageAnalysis:
        manifest = package.manifest
        package_name = self._package_name(package)
        all_dependencies = manifest.dependencies.all_dependency_names()
        local_dependencies = tuple(sorted(name for name in all_dependencies if name in self._workspace_model.workspace_package_names))
        external_dependencies = tuple(sorted(name for name in all_dependencies if name not in self._workspace_model.workspace_package_names))
        return NpmPackageAnalysis(
            package_name=package_name,
            package_path=package.repository_rel_path,
            manifest_path=package.package_json_rel_path,
            component_kind=self._classifier.component_kind_for(package),
            language=self._language_inferer.infer(package),
            source_roots=self._detect_source_roots(package),
            artifact_paths=self._detect_artifact_paths(package),
            local_dependencies=local_dependencies,
            external_dependencies=external_dependencies,
            manifest=manifest,
        )

    def _detect_source_roots(self, package: PackageJsonWorkspacePackage) -> tuple[str, ...]:
        found = set()
        for candidate in self._SOURCE_DIR_CANDIDATES:
            path = package.package_dir / candidate
            if path.is_dir():
                found.add(normalize_repository_relative_path(path.relative_to(self._workspace.repository_root).as_posix()))
        return tuple(sorted(found))

    def _detect_artifact_paths(self, package: PackageJsonWorkspacePackage) -> tuple[str, ...]:
        found: set[str] = set()
        for candidate in self._ARTIFACT_DIR_CANDIDATES:
            path = package.package_dir / candidate
            if path.exists():
                found.add(path.relative_to(self._workspace.repository_root).as_posix())
        for value in (package.manifest.main, package.manifest.module, package.manifest.types):
            if isinstance(value, str):
                self._add_existing_path(package, found, value)
        self._collect_export_paths(package, found, package.manifest.exports)
        bin_value = package.manifest.bin
        if isinstance(bin_value, str):
            self._add_existing_path(package, found, bin_value)
        elif isinstance(bin_value, dict):
            for value in bin_value.values():
                if isinstance(value, str):
                    self._add_existing_path(package, found, value)
        return tuple(sorted(found))

    def _collect_export_paths(self, package: PackageJsonWorkspacePackage, found: set[str], exports: object) -> None:
        if isinstance(exports, str):
            self._add_existing_path(package, found, exports)
            return
        if isinstance(exports, dict):
            for value in exports.values():
                self._collect_export_paths(package, found, value)
            return
        if isinstance(exports, list):
            for value in exports:
                self._collect_export_paths(package, found, value)

    def _add_existing_path(self, package: PackageJsonWorkspacePackage, found: set[str], candidate: str) -> None:
        path = package.package_dir / candidate
        if path.exists():
            found.add(path.relative_to(self._workspace.repository_root).as_posix())

    def _package_name(self, package: PackageJsonWorkspacePackage) -> str:
        if package.manifest.name is None:
            raise ValueError(f"workspace package missing name: {package.manifest.path}")
        return package.manifest.name
