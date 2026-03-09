from __future__ import annotations

from suitcode.core.models import Aggregator, Component, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.repository import Repository
from suitcode.mcp.models import (
    AggregatorView,
    ArchitectureSnapshotView,
    ComponentView,
    ExternalPackageView,
    FileView,
    PackageManagerView,
    RunnerView,
)
from suitcode.mcp.presenter_common import provenance_views


class ArchitecturePresenter:
    def component_view(self, component: Component) -> ComponentView:
        return ComponentView(
            id=component.id,
            name=component.name,
            component_kind=component.component_kind.value,
            language=component.language.value,
            source_roots=component.source_roots,
            artifact_paths=component.artifact_paths,
            provenance=provenance_views(component.provenance),
        )

    def aggregator_view(self, aggregator: Aggregator) -> AggregatorView:
        return AggregatorView(
            id=aggregator.id,
            name=aggregator.name,
            provenance=provenance_views(aggregator.provenance),
        )

    def runner_view(self, runner: Runner) -> RunnerView:
        return RunnerView(
            id=runner.id,
            name=runner.name,
            argv=runner.argv,
            cwd=runner.cwd,
            provenance=provenance_views(runner.provenance),
        )

    def package_manager_view(self, package_manager: PackageManager) -> PackageManagerView:
        return PackageManagerView(
            id=package_manager.id,
            name=package_manager.name,
            manager=package_manager.manager,
            lockfile_path=package_manager.lockfile_path,
            provenance=provenance_views(package_manager.provenance),
        )

    def external_package_view(self, external_package: ExternalPackage) -> ExternalPackageView:
        return ExternalPackageView(
            id=external_package.id,
            name=external_package.name,
            manager_id=external_package.manager_id,
            version_spec=external_package.version_spec,
            provenance=provenance_views(external_package.provenance),
        )

    def file_view(self, file_info: FileInfo) -> FileView:
        return FileView(
            id=file_info.id,
            path=file_info.repository_rel_path,
            language=file_info.language.value if file_info.language else None,
            owner_id=file_info.owner_id,
            provenance=provenance_views(file_info.provenance),
        )

    def architecture_snapshot(self, repository: Repository) -> ArchitectureSnapshotView:
        return ArchitectureSnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=tuple(provider.__class__.descriptor().provider_id for provider in repository.arch.providers),
            component_count=len(repository.arch.get_components()),
            aggregator_count=len(repository.arch.get_aggregators()),
            runner_count=len(repository.arch.get_runners()),
            package_manager_count=len(repository.arch.get_package_managers()),
            external_package_count=len(repository.arch.get_external_packages()),
            file_count=len(repository.arch.get_files()),
        )
