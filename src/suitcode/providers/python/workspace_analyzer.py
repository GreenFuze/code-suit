from __future__ import annotations

from pathlib import Path

from suitcode.providers.python.dependency_parser import PythonDependencyParser
from suitcode.providers.python.file_inventory import PythonOwnedFileInventoryBuilder
from suitcode.providers.python.models import (
    PythonExternalPackageAnalysis,
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
    PythonWorkspaceModel,
)
from suitcode.providers.python.package_discovery import PythonPackageDiscoverer
from suitcode.providers.shared.pyproject.models import PyProjectManifest


class PythonWorkspaceAnalyzer:
    def __init__(
        self,
        repository_root: Path,
        manifest: PyProjectManifest,
        package_discoverer: PythonPackageDiscoverer | None = None,
        dependency_parser: PythonDependencyParser | None = None,
        file_inventory_builder: PythonOwnedFileInventoryBuilder | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._manifest = manifest
        self._package_discoverer = package_discoverer or PythonPackageDiscoverer()
        self._dependency_parser = dependency_parser or PythonDependencyParser()
        self._file_inventory_builder = file_inventory_builder or PythonOwnedFileInventoryBuilder()
        self._components: tuple[PythonPackageComponentAnalysis, ...] | None = None
        self._runners: tuple[PythonRunnerAnalysis, ...] | None = None
        self._package_managers: tuple[PythonPackageManagerAnalysis, ...] | None = None
        self._external_packages: tuple[PythonExternalPackageAnalysis, ...] | None = None
        self._files: tuple[PythonOwnedFileAnalysis, ...] | None = None

    def model(self) -> PythonWorkspaceModel:
        return PythonWorkspaceModel(manifest=self._manifest, components=self.analyze_components())

    def analyze_components(self) -> tuple[PythonPackageComponentAnalysis, ...]:
        if self._components is None:
            self._components = self._package_discoverer.discover(self._repository_root, self._manifest)
        return self._components

    def analyze_aggregators(self) -> tuple[()]:
        return tuple()

    def analyze_runners(self) -> tuple[PythonRunnerAnalysis, ...]:
        if self._runners is None:
            runners: list[PythonRunnerAnalysis] = []
            project = self._manifest.project
            script_map: dict[str, str] = {}
            if project is not None:
                script_map.update(project.scripts)
                script_map.update(project.gui_scripts)
            for script_name in sorted(script_map):
                entrypoint = script_map[script_name]
                referenced_files = self._resolve_entrypoint_files(entrypoint)
                runners.append(
                    PythonRunnerAnalysis(
                        script_name=script_name,
                        entrypoint=entrypoint,
                        argv=('python-entrypoint', entrypoint),
                        cwd=None,
                        referenced_files=referenced_files,
                    )
                )
            self._runners = tuple(runners)
        return self._runners

    def analyze_package_managers(self) -> tuple[PythonPackageManagerAnalysis, ...]:
        if self._package_managers is None:
            self._package_managers = (
                PythonPackageManagerAnalysis(
                    node_id='pkgmgr:python:root',
                    display_name='python',
                    manager='python',
                    config_path='pyproject.toml',
                    owned_files=('pyproject.toml',),
                ),
            )
        return self._package_managers

    def analyze_external_packages(self) -> tuple[PythonExternalPackageAnalysis, ...]:
        if self._external_packages is None:
            manager_id = self.analyze_package_managers()[0].node_id
            self._external_packages = self._dependency_parser.parse(self._manifest, manager_id)
        return self._external_packages

    def analyze_files(self) -> tuple[PythonOwnedFileAnalysis, ...]:
        if self._files is None:
            self._files = self._file_inventory_builder.build(
                repository_root=self._repository_root,
                components=self.analyze_components(),
                runners=self.analyze_runners(),
                package_managers=self.analyze_package_managers(),
            )
        return self._files

    def _resolve_entrypoint_files(self, entrypoint: str) -> tuple[str, ...]:
        module_name = entrypoint.split(':', 1)[0].strip()
        if not module_name:
            return tuple()

        module_path = Path(*module_name.split('.'))
        candidates = (
            self._repository_root / 'src' / f'{module_path}.py',
            self._repository_root / 'src' / module_path / '__init__.py',
            self._repository_root / f'{module_path}.py',
            self._repository_root / module_path / '__init__.py',
        )
        for candidate in candidates:
            if candidate.exists():
                return (candidate.relative_to(self._repository_root).as_posix(),)
        return tuple()
