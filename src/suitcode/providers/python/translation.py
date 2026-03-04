from __future__ import annotations

from suitcode.core.models import Component, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.models.graph_types import ProgrammingLanguage
from suitcode.core.models.ids import make_file_id
from suitcode.providers.python.models import (
    PythonExternalPackageAnalysis,
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
)


class PythonModelTranslator:
    def to_component(self, item: PythonPackageComponentAnalysis) -> Component:
        return Component(
            id=f'component:python:{item.package_name}',
            name=item.package_name,
            component_kind=item.component_kind,
            language=ProgrammingLanguage.PYTHON,
            source_roots=item.source_roots,
            artifact_paths=item.artifact_paths,
        )

    def to_runner(self, item: PythonRunnerAnalysis) -> Runner:
        return Runner(
            id=f'runner:python:{item.script_name}',
            name=item.script_name,
            argv=item.argv,
            cwd=item.cwd,
        )

    def to_package_manager(self, item: PythonPackageManagerAnalysis) -> PackageManager:
        return PackageManager(
            id=item.node_id,
            name=item.display_name,
            manager=item.manager,
            lockfile_path=item.config_path,
        )

    def to_external_package(self, item: PythonExternalPackageAnalysis) -> ExternalPackage:
        return ExternalPackage(
            id=f'external:python:{item.package_name}',
            name=item.package_name,
            manager_id=item.manager_id,
            version_spec=item.version_spec,
        )

    def to_file_info(self, item: PythonOwnedFileAnalysis) -> FileInfo:
        return FileInfo(
            id=make_file_id(item.repository_rel_path),
            name=item.repository_rel_path,
            repository_rel_path=item.repository_rel_path,
            language=item.language,
            owner_id=item.owner_id,
        )
