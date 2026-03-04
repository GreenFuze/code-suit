from __future__ import annotations

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentContext, DependencyRef, FileContext, ImpactSummary, SymbolContext
from suitcode.core.models import Aggregator, Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.repository_models import FileOwnerInfo, OwnedNodeInfo
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch
from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_metadata import DetectedProviderSupport, ProviderDescriptor, RepositorySupportResult
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult
from suitcode.mcp.models import (
    AddRepositoryResult,
    AggregatorView,
    ArchitectureSnapshotView,
    ComponentContextView,
    ComponentView,
    DependencyRefView,
    DetectedProviderView,
    ExternalPackageView,
    FileContextView,
    FileView,
    FileOwnerView,
    ImpactSummaryView,
    OpenWorkspaceResult,
    LocationView,
    OwnerView,
    PackageManagerView,
    ProviderDescriptorView,
    QualityDiagnosticView,
    QualityEntityDeltaView,
    QualityFileResultView,
    QualitySnapshotView,
    RepositorySnapshotView,
    RepositorySummaryView,
    RepositorySupportView,
    RepositoryView,
    RunnerView,
    SymbolContextView,
    SymbolView,
    TestsSnapshotView,
    TestDefinitionView,
    RelatedTestView,
    WorkspaceSnapshotView,
    WorkspaceView,
)


def _sorted_role_values(roles: frozenset[ProviderRole]) -> tuple[str, ...]:
    return tuple(sorted(role.value for role in roles))


class ProviderPresenter:
    def descriptor_view(self, descriptor: ProviderDescriptor) -> ProviderDescriptorView:
        return ProviderDescriptorView(
            provider_id=descriptor.provider_id,
            display_name=descriptor.display_name,
            build_systems=descriptor.build_systems,
            programming_languages=descriptor.programming_languages,
            supported_roles=_sorted_role_values(descriptor.supported_roles),
        )

    def detected_view(self, detected: DetectedProviderSupport) -> DetectedProviderView:
        descriptor = detected.descriptor
        return DetectedProviderView(
            provider_id=descriptor.provider_id,
            display_name=descriptor.display_name,
            detected_roles=_sorted_role_values(detected.detected_roles),
            build_systems=descriptor.build_systems,
            programming_languages=descriptor.programming_languages,
        )

    def support_view(self, support: RepositorySupportResult) -> RepositorySupportView:
        return RepositorySupportView(
            repository_root=str(support.repository_root),
            is_supported=support.is_supported,
            detected_providers=tuple(self.detected_view(item) for item in support.detected_providers),
        )


class WorkspacePresenter:
    def workspace_view(self, workspace: Workspace) -> WorkspaceView:
        repository_ids = tuple(repository.id for repository in workspace.repositories)
        return WorkspaceView(
            workspace_id=workspace.id,
            repository_ids=repository_ids,
            repository_count=len(repository_ids),
        )

    def workspace_snapshot(self, workspace: Workspace) -> WorkspaceSnapshotView:
        repository_ids = tuple(repository.id for repository in workspace.repositories)
        return WorkspaceSnapshotView(
            workspace_id=workspace.id,
            repository_count=len(repository_ids),
            repository_ids=repository_ids,
        )

    def open_workspace_result(self, workspace: Workspace, repository: Repository, reused: bool) -> OpenWorkspaceResult:
        return OpenWorkspaceResult(
            workspace=self.workspace_view(workspace),
            initial_repository=RepositoryPresenter().repository_view(repository),
            reused=reused,
        )

    def add_repository_result(
        self,
        workspace_id: str,
        owning_workspace_id: str,
        repository: Repository,
        reused: bool,
    ) -> AddRepositoryResult:
        return AddRepositoryResult(
            workspace_id=workspace_id,
            repository=RepositoryPresenter().repository_view(repository),
            owning_workspace_id=owning_workspace_id,
            reused=reused,
        )


class RepositoryPresenter:
    def repository_view(self, repository: Repository) -> RepositoryView:
        return RepositoryView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            root_path=str(repository.root),
            suit_dir=str(repository.suit_dir),
            provider_ids=repository.provider_ids,
            provider_roles={
                provider_id: _sorted_role_values(roles)
                for provider_id, roles in repository.provider_roles.items()
            },
        )

    def repository_snapshot(self, repository: Repository) -> RepositorySnapshotView:
        return RepositorySnapshotView(**self.repository_view(repository).model_dump())


class ArchitecturePresenter:
    def component_view(self, component: Component) -> ComponentView:
        return ComponentView(
            id=component.id,
            name=component.name,
            component_kind=component.component_kind.value,
            language=component.language.value,
            source_roots=component.source_roots,
            artifact_paths=component.artifact_paths,
        )

    def aggregator_view(self, aggregator: Aggregator) -> AggregatorView:
        return AggregatorView(id=aggregator.id, name=aggregator.name)

    def runner_view(self, runner: Runner) -> RunnerView:
        return RunnerView(id=runner.id, name=runner.name, argv=runner.argv, cwd=runner.cwd)

    def package_manager_view(self, package_manager: PackageManager) -> PackageManagerView:
        return PackageManagerView(
            id=package_manager.id,
            name=package_manager.name,
            manager=package_manager.manager,
            lockfile_path=package_manager.lockfile_path,
        )

    def external_package_view(self, external_package: ExternalPackage) -> ExternalPackageView:
        return ExternalPackageView(
            id=external_package.id,
            name=external_package.name,
            manager_id=external_package.manager_id,
            version_spec=external_package.version_spec,
        )

    def file_view(self, file_info: FileInfo) -> FileView:
        return FileView(
            id=file_info.id,
            path=file_info.repository_rel_path,
            language=file_info.language.value if file_info.language else None,
            owner_id=file_info.owner_id,
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


class CodePresenter:
    def symbol_view(self, entity: EntityInfo) -> SymbolView:
        return SymbolView(
            id=entity.id,
            name=entity.name,
            kind=entity.entity_kind,
            path=entity.repository_rel_path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            column_start=entity.column_start,
            column_end=entity.column_end,
            signature=entity.signature,
        )

    def location_view(self, location: CodeLocation) -> LocationView:
        return LocationView(
            path=location.repository_rel_path,
            line_start=location.line_start,
            line_end=location.line_end,
            column_start=location.column_start,
            column_end=location.column_end,
            symbol_id=location.symbol_id,
        )


class TestPresenter:
    def test_view(self, discovered_test: DiscoveredTestDefinition) -> TestDefinitionView:
        test_definition = discovered_test.test_definition
        return TestDefinitionView(
            id=test_definition.id,
            name=test_definition.name,
            framework=test_definition.framework.value,
            test_files=test_definition.test_files,
            discovery_method=discovered_test.discovery_method.value,
            discovery_tool=discovered_test.discovery_tool,
            is_authoritative=discovered_test.is_authoritative,
        )

    def tests_snapshot(self, repository: Repository) -> TestsSnapshotView:
        return TestsSnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=tuple(provider.__class__.descriptor().provider_id for provider in repository.tests.providers),
            test_count=len(repository.tests.get_discovered_tests()),
        )

    def related_test_view(self, match: RelatedTestMatch, discovered_test: DiscoveredTestDefinition) -> RelatedTestView:
        return RelatedTestView(
            id=discovered_test.test_definition.id,
            name=discovered_test.test_definition.name,
            framework=discovered_test.test_definition.framework.value,
            test_files=discovered_test.test_definition.test_files,
            discovery_method=discovered_test.discovery_method.value,
            discovery_tool=discovered_test.discovery_tool,
            is_authoritative=discovered_test.is_authoritative,
            relation_reason=match.relation_reason,
            matched_owner_id=match.matched_owner_id,
            matched_path=match.matched_repository_rel_path,
        )


class QualityPresenter:
    def diagnostic_view(self, diagnostic: QualityDiagnostic) -> QualityDiagnosticView:
        return QualityDiagnosticView(**diagnostic.model_dump())

    def entity_delta_view(self, delta: QualityEntityDelta) -> QualityEntityDeltaView:
        code_presenter = CodePresenter()
        return QualityEntityDeltaView(
            added=tuple(code_presenter.symbol_view(item) for item in delta.added),
            removed=tuple(code_presenter.symbol_view(item) for item in delta.removed),
            updated=tuple(code_presenter.symbol_view(item) for item in delta.updated),
        )

    def quality_file_result_view(
        self,
        workspace_id: str,
        repository_id: str,
        provider_id: str,
        result: QualityFileResult,
    ) -> QualityFileResultView:
        return QualityFileResultView(
            workspace_id=workspace_id,
            repository_id=repository_id,
            provider_id=provider_id,
            repository_rel_path=result.repository_rel_path,
            tool=result.tool,
            operation=result.operation,
            changed=result.changed,
            success=result.success,
            message=result.message,
            diagnostics=tuple(self.diagnostic_view(item) for item in result.diagnostics),
            entity_delta=self.entity_delta_view(result.entity_delta),
            applied_fixes=result.applied_fixes,
            content_sha_before=result.content_sha_before,
            content_sha_after=result.content_sha_after,
        )

    def quality_snapshot(self, repository: Repository) -> QualitySnapshotView:
        return QualitySnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=repository.quality.provider_ids,
        )


class OwnershipPresenter:
    def owner_view(self, owner: OwnedNodeInfo) -> OwnerView:
        return OwnerView(id=owner.id, kind=owner.kind, name=owner.name)

    def file_owner_view(self, file_owner: FileOwnerInfo) -> FileOwnerView:
        file_view = ArchitecturePresenter().file_view(file_owner.file_info)
        return FileOwnerView(file=file_view, owner=self.owner_view(file_owner.owner))


class IntelligencePresenter:
    def dependency_ref_view(self, dependency_ref: DependencyRef) -> DependencyRefView:
        return DependencyRefView(**dependency_ref.model_dump())

    def component_context_view(self, context: ComponentContext) -> ComponentContextView:
        architecture_presenter = ArchitecturePresenter()
        return ComponentContextView(
            component=architecture_presenter.component_view(context.component),
            owned_file_count=context.owned_file_count,
            owned_files_preview=tuple(architecture_presenter.file_view(item) for item in context.owned_files_preview),
            runner_ids=context.runner_ids,
            related_test_ids=context.related_test_ids,
            dependency_count=context.dependency_count,
            dependencies_preview=tuple(self.dependency_ref_view(item) for item in context.dependencies_preview),
            dependent_count=context.dependent_count,
            dependents_preview=context.dependents_preview,
        )

    def file_context_view(self, context: FileContext) -> FileContextView:
        architecture_presenter = ArchitecturePresenter()
        code_presenter = CodePresenter()
        test_presenter = TestPresenter()
        ownership_presenter = OwnershipPresenter()
        return FileContextView(
            file=architecture_presenter.file_view(context.file_info),
            owner=ownership_presenter.owner_view(context.owner),
            symbol_count=context.symbol_count,
            symbols_preview=tuple(code_presenter.symbol_view(item) for item in context.symbols_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(
                test_presenter.related_test_view(
                    item,
                    DiscoveredTestDefinition(
                        test_definition=item.test_definition,
                        discovery_method=item.discovery_method,
                        discovery_tool=item.discovery_tool,
                        is_authoritative=item.is_authoritative,
                    ),
                )
                for item in context.related_tests_preview
            ),
            quality_provider_ids=context.quality_provider_ids,
        )

    def symbol_context_view(self, context: SymbolContext) -> SymbolContextView:
        code_presenter = CodePresenter()
        test_presenter = TestPresenter()
        ownership_presenter = OwnershipPresenter()
        return SymbolContextView(
            symbol=code_presenter.symbol_view(context.symbol),
            owner=ownership_presenter.owner_view(context.owner),
            definition_count=context.definition_count,
            definitions=tuple(code_presenter.location_view(item) for item in context.definitions),
            reference_count=context.reference_count,
            references_preview=tuple(code_presenter.location_view(item) for item in context.references_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(
                test_presenter.related_test_view(
                    item,
                    DiscoveredTestDefinition(
                        test_definition=item.test_definition,
                        discovery_method=item.discovery_method,
                        discovery_tool=item.discovery_tool,
                        is_authoritative=item.is_authoritative,
                    ),
                )
                for item in context.related_tests_preview
            ),
        )

    def impact_summary_view(self, summary: ImpactSummary) -> ImpactSummaryView:
        code_presenter = CodePresenter()
        ownership_presenter = OwnershipPresenter()
        return ImpactSummaryView(
            target_kind=summary.target_kind,
            owner=ownership_presenter.owner_view(summary.owner),
            primary_component_id=summary.primary_component_id,
            dependent_component_count=summary.dependent_component_count,
            dependent_component_ids_preview=summary.dependent_component_ids_preview,
            reference_count=summary.reference_count,
            references_preview=tuple(code_presenter.location_view(item) for item in summary.references_preview),
            related_test_count=summary.related_test_count,
            related_test_ids_preview=summary.related_test_ids_preview,
        )


class RepositorySummaryPresenter:
    def summary_view(self, repository: Repository, preview_limit: int) -> RepositorySummaryView:
        components = repository.arch.get_components()
        runners = repository.arch.get_runners()
        package_managers = repository.arch.get_package_managers()
        external_packages = repository.arch.get_external_packages()
        tests = repository.tests.get_discovered_tests()
        files = repository.arch.get_files()
        return RepositorySummaryView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=repository.provider_ids,
            provider_roles={
                provider_id: _sorted_role_values(roles)
                for provider_id, roles in repository.provider_roles.items()
            },
            quality_provider_ids=repository.quality.provider_ids,
            component_count=len(components),
            runner_count=len(runners),
            package_manager_count=len(package_managers),
            external_package_count=len(external_packages),
            test_count=len(tests),
            file_count=len(files),
            component_ids_preview=tuple(sorted(item.id for item in components)[:preview_limit]),
            runner_ids_preview=tuple(sorted(item.id for item in runners)[:preview_limit]),
            package_manager_ids_preview=tuple(sorted(item.id for item in package_managers)[:preview_limit]),
            test_ids_preview=tuple(sorted(item.test_definition.id for item in tests)[:preview_limit]),
            preview_limit=preview_limit,
        )
