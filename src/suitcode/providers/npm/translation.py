from __future__ import annotations

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    TestDefinition,
    Runner,
)
from suitcode.core.models.ids import make_file_id
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmExternalPackageAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)


class NpmModelTranslator:
    def to_component(self, analysis: NpmPackageAnalysis) -> Component:
        return Component(
            id=f"component:npm:{analysis.package_name}",
            name=analysis.package_name,
            component_kind=analysis.component_kind,
            language=analysis.language,
            source_roots=analysis.source_roots,
            artifact_paths=analysis.artifact_paths,
        )

    def to_aggregator(self, analysis: NpmAggregatorAnalysis) -> Aggregator:
        return Aggregator(
            id=f"aggregator:npm:{analysis.package_name}",
            name=analysis.package_name,
        )

    def to_runner(self, analysis: NpmRunnerAnalysis) -> Runner:
        return Runner(
            id=f"runner:npm:{analysis.package_name}:{analysis.script_name}",
            name=f"{analysis.package_name}:{analysis.script_name}",
            argv=analysis.argv,
            cwd=analysis.cwd,
        )

    def to_test_definition(self, analysis: NpmTestAnalysis) -> TestDefinition:
        return TestDefinition(
            id=f"test:npm:{analysis.package_name}",
            name=f"{analysis.package_name}:test",
            framework=analysis.framework,
            test_files=analysis.test_files,
        )

    def to_package_manager(self, analysis: NpmPackageManagerAnalysis) -> PackageManager:
        return PackageManager(
            id=analysis.node_id,
            name=analysis.display_name,
            manager=analysis.manager,
            lockfile_path=analysis.config_path,
        )

    def to_external_package(self, analysis: NpmExternalPackageAnalysis) -> ExternalPackage:
        return ExternalPackage(
            id=f"external:npm:{analysis.package_name}",
            name=analysis.package_name,
            manager_id=analysis.manager_id,
            version_spec=analysis.version_spec,
        )

    def to_file_info(self, analysis: NpmOwnedFileAnalysis) -> FileInfo:
        return FileInfo(
            id=make_file_id(analysis.repository_rel_path),
            name=analysis.repository_rel_path,
            repository_rel_path=analysis.repository_rel_path,
            language=analysis.language,
            owner_id=analysis.owner_id,
        )
