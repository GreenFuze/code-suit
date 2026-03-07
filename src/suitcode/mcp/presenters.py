from __future__ import annotations

from suitcode.analytics.models import AnalyticsSummary, BenchmarkReport, InefficiencyFinding, ToolUsageStats
from suitcode.core.action_models import RepositoryAction
from suitcode.core.code.models import CodeLocation
from suitcode.core.change_models import ChangeImpact, QualityGateInfo, RunnerImpact, TestImpact
from suitcode.core.intelligence_models import ComponentContext, ComponentDependencyEdge, DependencyRef, FileContext, ImpactSummary, SymbolContext
from suitcode.core.models import Aggregator, Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.build_models import BuildExecutionResult, BuildProjectResult, BuildTargetDescription
from suitcode.core.runner_models import RunnerContext, RunnerExecutionResult
from suitcode.core.repository_models import FileOwnerInfo, OwnedNodeInfo
from suitcode.core.tests.models import DiscoveredTestDefinition, ResolvedRelatedTest
from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_metadata import DetectedProviderSupport, ProviderDescriptor, RepositorySupportResult
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult
from suitcode.mcp.models import (
    AddRepositoryResult,
    AggregatorView,
    AnalyticsSummaryView,
    ActionInvocationView,
    ActionView,
    ArchitectureSnapshotView,
    BenchmarkReportView,
    BenchmarkTaskResultView,
    BuildExecutionResultView,
    BuildProjectResultView,
    BuildTargetDescriptionView,
    ComponentContextView,
    ComponentView,
    ComponentDependencyEdgeView,
    DependencyRefView,
    DetectedProviderView,
    ExternalPackageView,
    FileContextView,
    FileView,
    FileOwnerView,
    ImpactSummaryView,
    InefficientToolCallView,
    ChangeImpactView,
    OpenWorkspaceResult,
    LocationView,
    OwnerView,
    PackageManagerView,
    ProvenanceView,
    ProviderDescriptorView,
    QualityDiagnosticView,
    QualityEntityDeltaView,
    QualityFileResultView,
    QualityGateView,
    QualitySnapshotView,
    RepositorySnapshotView,
    RepositorySummaryView,
    RepositorySupportView,
    RepositoryView,
    RunnerContextView,
    RunnerExecutionResultView,
    RunnerView,
    RunnerImpactView,
    SymbolContextView,
    SymbolView,
    TestsSnapshotView,
    TestDefinitionView,
    RelatedTestView,
    RunTestTargetsView,
    TestImpactView,
    TestExecutionResultView,
    TestFailureSnippetView,
    WorkspaceSnapshotView,
    WorkspaceView,
    TestTargetDescriptionView,
    ToolUsageAnalyticsView,
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
    def __init__(self) -> None:
        self._repository_presenter = RepositoryPresenter()

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
            initial_repository=self._repository_presenter.repository_view(repository),
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
            repository=self._repository_presenter.repository_view(repository),
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
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

    def _provenance_views(self, items: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceView, ...]:
        return tuple(self._intelligence_presenter.provenance_view(item) for item in items)

    def component_view(self, component: Component) -> ComponentView:
        return ComponentView(
            id=component.id,
            name=component.name,
            component_kind=component.component_kind.value,
            language=component.language.value,
            source_roots=component.source_roots,
            artifact_paths=component.artifact_paths,
            provenance=self._provenance_views(component.provenance),
        )

    def aggregator_view(self, aggregator: Aggregator) -> AggregatorView:
        return AggregatorView(
            id=aggregator.id,
            name=aggregator.name,
            provenance=self._provenance_views(aggregator.provenance),
        )

    def runner_view(self, runner: Runner) -> RunnerView:
        return RunnerView(
            id=runner.id,
            name=runner.name,
            argv=runner.argv,
            cwd=runner.cwd,
            provenance=self._provenance_views(runner.provenance),
        )

    def package_manager_view(self, package_manager: PackageManager) -> PackageManagerView:
        return PackageManagerView(
            id=package_manager.id,
            name=package_manager.name,
            manager=package_manager.manager,
            lockfile_path=package_manager.lockfile_path,
            provenance=self._provenance_views(package_manager.provenance),
        )

    def external_package_view(self, external_package: ExternalPackage) -> ExternalPackageView:
        return ExternalPackageView(
            id=external_package.id,
            name=external_package.name,
            manager_id=external_package.manager_id,
            version_spec=external_package.version_spec,
            provenance=self._provenance_views(external_package.provenance),
        )

    def file_view(self, file_info: FileInfo) -> FileView:
        return FileView(
            id=file_info.id,
            path=file_info.repository_rel_path,
            language=file_info.language.value if file_info.language else None,
            owner_id=file_info.owner_id,
            provenance=self._provenance_views(file_info.provenance),
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
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

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
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in entity.provenance),
        )

    def location_view(self, location: CodeLocation) -> LocationView:
        return LocationView(
            path=location.repository_rel_path,
            line_start=location.line_start,
            line_end=location.line_end,
            column_start=location.column_start,
            column_end=location.column_end,
            symbol_id=location.symbol_id,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in location.provenance),
        )


class TestPresenter:
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

    def _provenance_views(self, items: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceView, ...]:
        return tuple(self._intelligence_presenter.provenance_view(item) for item in items)

    def test_view(self, discovered_test: DiscoveredTestDefinition) -> TestDefinitionView:
        test_definition = discovered_test.test_definition
        return TestDefinitionView(
            id=test_definition.id,
            name=test_definition.name,
            framework=test_definition.framework.value,
            test_files=test_definition.test_files,
            provenance=self._provenance_views(discovered_test.provenance),
        )

    def tests_snapshot(self, repository: Repository) -> TestsSnapshotView:
        return TestsSnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=tuple(provider.__class__.descriptor().provider_id for provider in repository.tests.providers),
            test_count=len(repository.tests.get_discovered_tests()),
        )

    def related_test_view(self, related_test: ResolvedRelatedTest) -> RelatedTestView:
        match = related_test.match
        discovered_test = related_test.discovered_test
        return RelatedTestView(
            id=discovered_test.test_definition.id,
            name=discovered_test.test_definition.name,
            framework=discovered_test.test_definition.framework.value,
            test_files=discovered_test.test_definition.test_files,
            relation_reason=match.relation_reason,
            matched_owner_id=match.matched_owner_id,
            matched_path=match.matched_repository_rel_path,
            provenance=self._provenance_views(related_test.provenance),
        )

    def test_target_description_view(self, description) -> TestTargetDescriptionView:
        test_definition = description.test_definition
        return TestTargetDescriptionView(
            id=test_definition.id,
            name=test_definition.name,
            framework=test_definition.framework.value,
            test_files=test_definition.test_files,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            is_authoritative=description.is_authoritative,
            warning=description.warning,
            provenance=self._provenance_views(description.provenance),
        )

    def test_execution_result_view(self, result) -> TestExecutionResultView:
        return TestExecutionResultView(
            test_id=result.test_id,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            warning=result.warning,
            output_excerpt=result.output_excerpt,
            failure_snippets=tuple(
                TestFailureSnippetView(
                    repository_rel_path=item.repository_rel_path,
                    line_start=item.line_start,
                    line_end=item.line_end,
                    snippet=item.snippet,
                    provenance=self._provenance_views(item.provenance),
                )
                for item in result.failure_snippets
            ),
            provenance=self._provenance_views(result.provenance),
        )

    def run_test_targets_view(
        self,
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
        results,
    ) -> RunTestTargetsView:
        views = tuple(self.test_execution_result_view(item) for item in results)
        passed = sum(1 for item in views if item.status == "passed")
        failed = sum(1 for item in views if item.status == "failed")
        errors = sum(1 for item in views if item.status == "error")
        timeouts = sum(1 for item in views if item.status == "timeout")
        return RunTestTargetsView(
            workspace_id=workspace_id,
            repository_id=repository_id,
            timeout_seconds=timeout_seconds,
            total=len(views),
            passed=passed,
            failed=failed,
            errors=errors,
            timeouts=timeouts,
            results=views,
        )


class RunnerPresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()
        self._test_presenter = TestPresenter()
        self._intelligence_presenter = IntelligencePresenter()

    def runner_context_view(self, context: RunnerContext) -> RunnerContextView:
        return RunnerContextView(
            runner=self._architecture_presenter.runner_view(context.runner),
            action_id=context.action_id,
            provider_id=context.provider_id,
            invocation=ActionInvocationView(argv=context.invocation.argv, cwd=context.invocation.cwd),
            primary_component=(
                self._architecture_presenter.component_view(context.primary_component)
                if context.primary_component is not None
                else None
            ),
            owned_file_count=context.owned_file_count,
            owned_files_preview=tuple(self._architecture_presenter.file_view(item) for item in context.owned_files_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(self._test_presenter.related_test_view(item) for item in context.related_tests_preview),
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in context.provenance),
        )

    def runner_execution_result_view(self, result: RunnerExecutionResult) -> RunnerExecutionResultView:
        return RunnerExecutionResultView(
            runner_id=result.runner_id,
            action_id=result.action_id,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            output_excerpt=result.output_excerpt,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in result.provenance),
        )


class BuildPresenter:
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

    def build_target_description_view(self, target: BuildTargetDescription) -> BuildTargetDescriptionView:
        return BuildTargetDescriptionView(
            action_id=target.action_id,
            name=target.name,
            provider_id=target.provider_id,
            target_id=target.target_id,
            target_kind=target.target_kind.value,
            owner_ids=target.owner_ids,
            invocation=ActionInvocationView(argv=target.invocation.argv, cwd=target.invocation.cwd),
            dry_run_supported=target.dry_run_supported,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in target.provenance),
        )

    def build_execution_result_view(self, result: BuildExecutionResult) -> BuildExecutionResultView:
        return BuildExecutionResultView(
            action_id=result.action_id,
            target_id=result.target_id,
            target_kind=result.target_kind.value,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            output_excerpt=result.output_excerpt,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in result.provenance),
        )

    def build_project_result_view(self, result: BuildProjectResult) -> BuildProjectResultView:
        return BuildProjectResultView(
            timeout_seconds=result.timeout_seconds,
            total=result.total,
            passed=result.passed,
            failed=result.failed,
            errors=result.errors,
            timeouts=result.timeouts,
            succeeded_target_ids=result.succeeded_target_ids,
            failed_results=tuple(self.build_execution_result_view(item) for item in result.failed_results),
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in result.provenance),
        )


class QualityPresenter:
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()
        self._code_presenter = CodePresenter()

    def diagnostic_view(self, diagnostic: QualityDiagnostic) -> QualityDiagnosticView:
        return QualityDiagnosticView(
            **diagnostic.model_dump(exclude={"provenance"}),
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in diagnostic.provenance),
        )

    def entity_delta_view(self, delta: QualityEntityDelta) -> QualityEntityDeltaView:
        return QualityEntityDeltaView(
            added=tuple(self._code_presenter.symbol_view(item) for item in delta.added),
            removed=tuple(self._code_presenter.symbol_view(item) for item in delta.removed),
            updated=tuple(self._code_presenter.symbol_view(item) for item in delta.updated),
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in delta.provenance),
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
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in result.provenance),
        )

    def quality_snapshot(self, repository: Repository) -> QualitySnapshotView:
        return QualitySnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=repository.quality.provider_ids,
        )


class OwnershipPresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()

    def owner_view(self, owner: OwnedNodeInfo) -> OwnerView:
        return OwnerView(id=owner.id, kind=owner.kind, name=owner.name)

    def file_owner_view(self, file_owner: FileOwnerInfo) -> FileOwnerView:
        file_view = self._architecture_presenter.file_view(file_owner.file_info)
        return FileOwnerView(file=file_view, owner=self.owner_view(file_owner.owner))


class IntelligencePresenter:
    def provenance_view(self, provenance: ProvenanceEntry) -> ProvenanceView:
        return ProvenanceView(
            confidence_mode=provenance.confidence_mode.value,
            source_kind=provenance.source_kind.value,
            source_tool=provenance.source_tool,
            evidence_summary=provenance.evidence_summary,
            evidence_paths=provenance.evidence_paths,
        )

    def dependency_ref_view(self, dependency_ref: DependencyRef) -> DependencyRefView:
        return DependencyRefView(
            target_id=dependency_ref.target_id,
            target_kind=dependency_ref.target_kind,
            dependency_scope=dependency_ref.dependency_scope,
            provenance=tuple(self.provenance_view(item) for item in dependency_ref.provenance),
        )

    def component_dependency_edge_view(self, edge: ComponentDependencyEdge) -> ComponentDependencyEdgeView:
        return ComponentDependencyEdgeView(
            source_component_id=edge.source_component_id,
            target_id=edge.target_id,
            target_kind=edge.target_kind,
            dependency_scope=edge.dependency_scope,
            provenance=tuple(self.provenance_view(item) for item in edge.provenance),
        )

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
            provenance=tuple(self.provenance_view(item) for item in context.provenance),
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
            related_tests_preview=tuple(test_presenter.related_test_view(item) for item in context.related_tests_preview),
            quality_provider_ids=context.quality_provider_ids,
            provenance=tuple(self.provenance_view(item) for item in context.provenance),
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
            related_tests_preview=tuple(test_presenter.related_test_view(item) for item in context.related_tests_preview),
            provenance=tuple(self.provenance_view(item) for item in context.provenance),
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
            provenance=tuple(self.provenance_view(item) for item in summary.provenance),
        )


class ChangeImpactPresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()
        self._code_presenter = CodePresenter()
        self._test_presenter = TestPresenter()
        self._ownership_presenter = OwnershipPresenter()
        self._intelligence_presenter = IntelligencePresenter()

    def quality_gate_view(self, gate: QualityGateInfo) -> QualityGateView:
        return QualityGateView(
            provider_id=gate.provider_id,
            provider_roles=gate.provider_roles,
            applies=gate.applies,
            reason=gate.reason,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in gate.provenance),
        )

    def runner_impact_view(self, runner_impact: RunnerImpact) -> RunnerImpactView:
        return RunnerImpactView(
            runner=self._architecture_presenter.runner_view(runner_impact.runner),
            reason=runner_impact.reason,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in runner_impact.provenance),
        )

    def test_impact_view(self, test_impact: TestImpact) -> TestImpactView:
        return TestImpactView(
            test=self._test_presenter.related_test_view(test_impact.related_test),
            reason=test_impact.reason,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in test_impact.provenance),
        )

    def change_impact_view(self, impact: ChangeImpact) -> ChangeImpactView:
        return ChangeImpactView(
            target_kind=impact.target_kind,
            owner=self._ownership_presenter.owner_view(impact.owner),
            primary_component=(
                self._architecture_presenter.component_view(impact.primary_component)
                if impact.primary_component is not None
                else None
            ),
            component_context=(
                self._intelligence_presenter.component_context_view(impact.component_context)
                if impact.component_context is not None
                else None
            ),
            file_context=(
                self._intelligence_presenter.file_context_view(impact.file_context)
                if impact.file_context is not None
                else None
            ),
            symbol_context=(
                self._intelligence_presenter.symbol_context_view(impact.symbol_context)
                if impact.symbol_context is not None
                else None
            ),
            dependent_components=tuple(
                self._architecture_presenter.component_view(item) for item in impact.dependent_components
            ),
            reference_locations=tuple(self._code_presenter.location_view(item) for item in impact.reference_locations),
            related_tests=tuple(self.test_impact_view(item) for item in impact.related_tests),
            related_runners=tuple(self.runner_impact_view(item) for item in impact.related_runners),
            quality_gates=tuple(self.quality_gate_view(item) for item in impact.quality_gates),
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in impact.provenance),
        )


class ActionPresenter:
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

    def action_view(self, action: RepositoryAction) -> ActionView:
        return ActionView(
            id=action.id,
            name=action.name,
            kind=action.kind.value,
            provider_id=action.provider_id,
            target_id=action.target_id,
            target_kind=action.target_kind.value,
            owner_ids=action.owner_ids,
            invocation=ActionInvocationView(argv=action.invocation.argv, cwd=action.invocation.cwd),
            dry_run_supported=action.dry_run_supported,
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in action.provenance),
        )


class RepositorySummaryPresenter:
    def __init__(self) -> None:
        self._intelligence_presenter = IntelligencePresenter()

    def summary_view(self, repository: Repository, preview_limit: int) -> RepositorySummaryView:
        components = repository.arch.get_components()
        runners = repository.arch.get_runners()
        package_managers = repository.arch.get_package_managers()
        external_packages = repository.arch.get_external_packages()
        tests = repository.tests.get_discovered_tests()
        files = repository.arch.get_files()
        provenance_entries = [
            derived_summary_provenance(
                source_kind=SourceKind.MANIFEST,
                evidence_summary="repository summary derived from provider-backed architecture metadata",
                evidence_paths=tuple(pm.lockfile_path for pm in package_managers if pm.lockfile_path)[:10],
            )
        ]
        if tests:
            test_paths: list[str] = []
            for item in tests:
                for provenance in item.provenance:
                    for path in provenance.evidence_paths:
                        if path not in test_paths:
                            test_paths.append(path)
            provenance_entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.TEST_TOOL,
                    evidence_summary="repository summary includes discovered test metadata",
                    evidence_paths=tuple(test_paths[:10]),
                )
            )
        if files:
            provenance_entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.OWNERSHIP,
                    evidence_summary="repository summary includes file ownership counts",
                    evidence_paths=tuple(file.repository_rel_path for file in files[:10]),
                )
            )
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
            provenance=tuple(self._intelligence_presenter.provenance_view(item) for item in provenance_entries),
        )


class AnalyticsPresenter:
    def summary_view(self, summary: AnalyticsSummary) -> AnalyticsSummaryView:
        return AnalyticsSummaryView(**summary.model_dump())

    def tool_usage_view(self, stats: ToolUsageStats) -> ToolUsageAnalyticsView:
        return ToolUsageAnalyticsView(**stats.model_dump())

    def inefficiency_view(self, finding: InefficiencyFinding) -> InefficientToolCallView:
        return InefficientToolCallView(**finding.model_dump())

    def benchmark_report_view(self, report: BenchmarkReport) -> BenchmarkReportView:
        return BenchmarkReportView(
            schema_version=report.schema_version,
            report_id=report.report_id,
            generated_at_utc=report.generated_at_utc,
            adapter_name=report.adapter_name,
            task_total=report.task_total,
            task_passed=report.task_passed,
            task_failed=report.task_failed,
            task_error=report.task_error,
            avg_tool_calls=report.avg_tool_calls,
            avg_duration_ms=report.avg_duration_ms,
            tasks=tuple(BenchmarkTaskResultView(**item.model_dump()) for item in report.tasks),
        )
