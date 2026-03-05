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
from suitcode.core.provenance_builders import (
    heuristic_provenance,
    manifest_node_provenance,
    manifest_provenance,
    ownership_node_provenance,
    test_tool_provenance,
)
from suitcode.core.tests.models import DiscoveredTestDefinition, TestDiscoveryMethod
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
    def _test_provenance(self, analysis: NpmTestAnalysis):
        if analysis.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS:
            return (
                test_tool_provenance(
                    source_tool="jest",
                    evidence_summary="discovered from jest --listTests",
                    evidence_paths=analysis.evidence_paths,
                ),
            )
        return (
            heuristic_provenance(
                evidence_summary="derived from package manifest test script metadata and test file globs",
                evidence_paths=analysis.evidence_paths,
            ),
        )

    def to_component(self, analysis: NpmPackageAnalysis) -> Component:
        return Component(
            id=f"component:npm:{analysis.package_name}",
            name=analysis.package_name,
            component_kind=analysis.component_kind,
            language=analysis.language,
            source_roots=analysis.source_roots,
            artifact_paths=analysis.artifact_paths,
            provenance=(
                manifest_provenance(
                    evidence_summary="derived from npm workspace package metadata",
                    evidence_paths=(analysis.manifest_path,),
                ),
            ),
        )

    def to_aggregator(self, analysis: NpmAggregatorAnalysis) -> Aggregator:
        return Aggregator(
            id=f"aggregator:npm:{analysis.package_name}",
            name=analysis.package_name,
            provenance=(
                manifest_node_provenance(
                    evidence_summary="derived from npm workspace package metadata and aggregator classification",
                    evidence_paths=(analysis.manifest_path,),
                ),
            ),
        )

    def to_runner(self, analysis: NpmRunnerAnalysis) -> Runner:
        return Runner(
            id=f"runner:npm:{analysis.package_name}:{analysis.script_name}",
            name=f"{analysis.package_name}:{analysis.script_name}",
            argv=analysis.argv,
            cwd=analysis.cwd,
            provenance=(
                manifest_provenance(
                    evidence_summary="derived from npm package script metadata",
                    evidence_paths=(f"{analysis.package_path}/package.json",),
                ),
            ),
        )

    def to_test_definition(self, analysis: NpmTestAnalysis) -> TestDefinition:
        return TestDefinition(
            id=f"test:npm:{analysis.package_name}",
            name=f"{analysis.package_name}:test",
            framework=analysis.framework,
            test_files=analysis.test_files,
            provenance=self._test_provenance(analysis),
        )

    def to_discovered_test_definition(self, analysis: NpmTestAnalysis) -> DiscoveredTestDefinition:
        return DiscoveredTestDefinition(
            test_definition=self.to_test_definition(analysis),
            provenance=self._test_provenance(analysis),
        )

    def to_package_manager(self, analysis: NpmPackageManagerAnalysis) -> PackageManager:
        evidence_paths = tuple(
            path
            for path in ((analysis.config_path,) if analysis.config_path else tuple())
        ) or analysis.owned_files
        return PackageManager(
            id=analysis.node_id,
            name=analysis.display_name,
            manager=analysis.manager,
            lockfile_path=analysis.config_path,
            provenance=(
                manifest_node_provenance(
                    evidence_summary="derived from npm ecosystem config and manifest detection",
                    evidence_paths=evidence_paths,
                ),
            ),
        )

    def to_external_package(self, analysis: NpmExternalPackageAnalysis) -> ExternalPackage:
        return ExternalPackage(
            id=f"external:npm:{analysis.package_name}",
            name=analysis.package_name,
            manager_id=analysis.manager_id,
            version_spec=analysis.version_spec,
            provenance=(
                manifest_provenance(
                    evidence_summary="derived from npm dependency metadata",
                    evidence_paths=analysis.evidence_paths,
                ),
            ),
        )

    def to_file_info(self, analysis: NpmOwnedFileAnalysis) -> FileInfo:
        return FileInfo(
            id=make_file_id(analysis.repository_rel_path),
            name=analysis.repository_rel_path,
            repository_rel_path=analysis.repository_rel_path,
            language=analysis.language,
            owner_id=analysis.owner_id,
            provenance=(
                ownership_node_provenance(
                    evidence_summary="assigned to an owner using npm provider ownership derivation",
                    evidence_paths=(analysis.repository_rel_path,),
                ),
            ),
        )
