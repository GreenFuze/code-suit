from __future__ import annotations

from suitcode.core.change_models import ChangeEvidenceEdge, ChangeEvidencePreview, ChangeImpact, QualityGateInfo, RunnerImpact, TestImpact
from suitcode.core.intelligence_models import ComponentContext, ComponentDependencyEdge, DependencyRef, FileContext, ImpactSummary, SymbolContext
from suitcode.core.minimum_verified_change_set_models import (
    ExcludedMinimumVerifiedItem,
    MinimumVerifiedBuildTarget,
    MinimumVerifiedChangeSet,
    MinimumVerifiedEvidenceEdge,
    MinimumVerifiedQualityOperation,
    MinimumVerifiedRunnerAction,
    MinimumVerifiedTestTarget,
)
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.repository import Repository
from suitcode.core.truth_coverage_models import TruthCoverageByDomain, TruthCoverageSummary
from suitcode.mcp.models import (
    ChangeImpactView,
    ChangeEvidenceEdgeView,
    ChangeEvidencePreviewView,
    ComponentContextView,
    ComponentDependencyEdgeView,
    DependencyRefView,
    ExcludedMinimumVerifiedItemView,
    FileContextView,
    ImpactSummaryView,
    MinimumVerifiedBuildTargetView,
    MinimumVerifiedCommandSummaryView,
    MinimumVerifiedChangeSetView,
    MinimumVerifiedEvidenceEdgeView,
    MinimumVerifiedQualityOperationView,
    MinimumVerifiedRunnerActionView,
    MinimumVerifiedTestTargetView,
    QualityGateView,
    RepositorySummaryView,
    RunnerImpactView,
    SymbolContextView,
    TestImpactView,
    TruthCoverageByDomainView,
    TruthCoverageSummaryView,
)
from suitcode.mcp.presenter_architecture import ArchitecturePresenter
from suitcode.mcp.presenter_code import CodePresenter
from suitcode.mcp.presenter_common import compact_provenance_views, provenance_view, provenance_views, sorted_role_values
from suitcode.mcp.presenter_repository import OwnershipPresenter
from suitcode.mcp.presenter_tests import TestPresenter


class IntelligencePresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()
        self._code_presenter = CodePresenter()
        self._test_presenter = TestPresenter()
        self._ownership_presenter = OwnershipPresenter(self._architecture_presenter)

    def provenance_view(self, provenance: ProvenanceEntry):
        return provenance_view(provenance)

    def truth_coverage_domain_view(self, domain: TruthCoverageByDomain) -> TruthCoverageByDomainView:
        return TruthCoverageByDomainView(
            domain=domain.domain.value,
            total_entities=domain.total_entities,
            authoritative_count=domain.authoritative_count,
            derived_count=domain.derived_count,
            heuristic_count=domain.heuristic_count,
            unavailable_count=domain.unavailable_count,
            availability=domain.availability.value,
            degraded_reason=domain.degraded_reason,
            source_kind_mix=domain.source_kind_mix,
            source_tool_mix=domain.source_tool_mix,
            execution_available=domain.execution_available,
            action_capabilities=domain.action_capabilities,
        )

    def truth_coverage_summary_view(self, summary: TruthCoverageSummary) -> TruthCoverageSummaryView:
        return TruthCoverageSummaryView(
            scope_kind=summary.scope_kind,
            scope_id=summary.scope_id,
            domains=tuple(self.truth_coverage_domain_view(item) for item in summary.domains),
            overall_authoritative_count=summary.overall_authoritative_count,
            overall_derived_count=summary.overall_derived_count,
            overall_heuristic_count=summary.overall_heuristic_count,
            overall_unavailable_count=summary.overall_unavailable_count,
            overall_availability=summary.overall_availability.value,
            provenance=provenance_views(summary.provenance),
        )

    def dependency_ref_view(self, dependency_ref: DependencyRef) -> DependencyRefView:
        return DependencyRefView(
            target_id=dependency_ref.target_id,
            target_kind=dependency_ref.target_kind,
            dependency_scope=dependency_ref.dependency_scope,
            provenance=provenance_views(dependency_ref.provenance),
        )

    def component_dependency_edge_view(self, edge: ComponentDependencyEdge) -> ComponentDependencyEdgeView:
        return ComponentDependencyEdgeView(
            source_component_id=edge.source_component_id,
            target_id=edge.target_id,
            target_kind=edge.target_kind,
            dependency_scope=edge.dependency_scope,
            provenance=provenance_views(edge.provenance),
        )

    def component_context_view(self, context: ComponentContext) -> ComponentContextView:
        return ComponentContextView(
            component=self._architecture_presenter.component_view(context.component),
            owned_file_count=context.owned_file_count,
            owned_files_preview=tuple(self._architecture_presenter.file_view(item) for item in context.owned_files_preview),
            runner_ids=context.runner_ids,
            related_test_ids=context.related_test_ids,
            dependency_count=context.dependency_count,
            dependencies_preview=tuple(self.dependency_ref_view(item) for item in context.dependencies_preview),
            dependent_count=context.dependent_count,
            dependents_preview=context.dependents_preview,
            provenance=provenance_views(context.provenance),
        )

    def file_context_view(self, context: FileContext) -> FileContextView:
        return FileContextView(
            file=self._architecture_presenter.file_view(context.file_info),
            owner=self._ownership_presenter.owner_view(context.owner),
            symbol_count=context.symbol_count,
            symbols_preview=tuple(self._code_presenter.symbol_view(item) for item in context.symbols_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(self._test_presenter.related_test_view(item) for item in context.related_tests_preview),
            quality_provider_ids=context.quality_provider_ids,
            provenance=provenance_views(context.provenance),
        )

    def symbol_context_view(self, context: SymbolContext) -> SymbolContextView:
        return SymbolContextView(
            symbol=self._code_presenter.symbol_view(context.symbol),
            owner=self._ownership_presenter.owner_view(context.owner),
            definition_count=context.definition_count,
            definitions=tuple(self._code_presenter.location_view(item) for item in context.definitions),
            reference_count=context.reference_count,
            references_preview=tuple(self._code_presenter.location_view(item) for item in context.references_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(self._test_presenter.related_test_view(item) for item in context.related_tests_preview),
            provenance=provenance_views(context.provenance),
        )

    def impact_summary_view(self, summary: ImpactSummary) -> ImpactSummaryView:
        return ImpactSummaryView(
            target_kind=summary.target_kind,
            owner=self._ownership_presenter.owner_view(summary.owner),
            primary_component_id=summary.primary_component_id,
            dependent_component_count=summary.dependent_component_count,
            dependent_component_ids_preview=summary.dependent_component_ids_preview,
            reference_count=summary.reference_count,
            references_preview=tuple(self._code_presenter.location_view(item) for item in summary.references_preview),
            related_test_count=summary.related_test_count,
            related_test_ids_preview=summary.related_test_ids_preview,
            provenance=provenance_views(summary.provenance),
        )


class ChangeImpactPresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()
        self._code_presenter = CodePresenter()
        self._test_presenter = TestPresenter()
        self._ownership_presenter = OwnershipPresenter(self._architecture_presenter)
        self._intelligence_presenter = IntelligencePresenter()
        from suitcode.mcp.presenter_execution import ActionPresenter, BuildPresenter

        self._action_presenter = ActionPresenter()
        self._build_presenter = BuildPresenter()

    def quality_gate_view(self, gate: QualityGateInfo) -> QualityGateView:
        return QualityGateView(
            provider_id=gate.provider_id,
            provider_roles=gate.provider_roles,
            applies=gate.applies,
            reason=gate.reason,
            provenance=compact_provenance_views(gate.provenance),
        )

    def runner_impact_view(self, runner_impact: RunnerImpact) -> RunnerImpactView:
        return RunnerImpactView(
            runner=self._architecture_presenter.runner_view(
                runner_impact.runner.model_copy(update={"argv": runner_impact.runner.argv[:6]})
            ),
            reason=runner_impact.reason,
            provenance=compact_provenance_views(runner_impact.provenance),
        )

    def test_impact_view(self, test_impact: TestImpact) -> TestImpactView:
        return TestImpactView(
            test=self._test_presenter.related_test_view(test_impact.related_test),
            reason=test_impact.reason,
            provenance=compact_provenance_views(test_impact.provenance),
        )

    def change_evidence_edge_view(self, edge: ChangeEvidenceEdge) -> ChangeEvidenceEdgeView:
        return ChangeEvidenceEdgeView(
            source_node_kind=edge.source_node_kind,
            source_node_id=edge.source_node_id,
            target_node_kind=edge.target_node_kind,
            target_node_id=edge.target_node_id,
            edge_kind=edge.edge_kind.value,
            reason=edge.reason,
            provenance=compact_provenance_views(edge.provenance),
        )

    def change_evidence_preview_view(self, preview: ChangeEvidencePreview) -> ChangeEvidencePreviewView:
        preview_edges = preview.edges_preview[:10]
        return ChangeEvidencePreviewView(
            total_edges=preview.total_edges,
            counts_by_kind=preview.counts_by_kind,
            edges_preview=tuple(self.change_evidence_edge_view(item) for item in preview_edges),
            truncated=preview.truncated or len(preview.edges_preview) > len(preview_edges),
        )

    def minimum_verified_evidence_edge_view(self, edge: MinimumVerifiedEvidenceEdge) -> MinimumVerifiedEvidenceEdgeView:
        return MinimumVerifiedEvidenceEdgeView(
            source_node_kind=edge.source_node_kind,
            source_node_id=edge.source_node_id,
            target_node_kind=edge.target_node_kind,
            target_node_id=edge.target_node_id,
            edge_kind=edge.edge_kind.value,
            reason=edge.reason,
            provenance=compact_provenance_views(edge.provenance),
        )

    @staticmethod
    def minimum_verified_command_summary_view(
        argv: tuple[str, ...],
        *,
        cwd: str | None,
        preview_limit: int = 8,
    ) -> MinimumVerifiedCommandSummaryView:
        return MinimumVerifiedCommandSummaryView(
            argv_preview=argv[:preview_limit],
            total_arg_count=len(argv),
            truncated=len(argv) > preview_limit,
            cwd=cwd,
        )

    def minimum_verified_test_target_view(self, item: MinimumVerifiedTestTarget) -> MinimumVerifiedTestTargetView:
        return MinimumVerifiedTestTargetView(
            test_id=item.target.test_definition.id,
            name=item.target.test_definition.name,
            framework=item.target.test_definition.framework.value,
            test_file_count=len(item.target.test_definition.test_files),
            test_files_preview=item.target.test_definition.test_files[:5],
            command=self.minimum_verified_command_summary_view(
                item.target.command_argv,
                cwd=item.target.command_cwd,
            ),
            is_authoritative=item.target.is_authoritative,
            warning=item.target.warning,
            inclusion_reason=item.inclusion_reason,
            inclusion_confidence_mode=item.inclusion_confidence_mode.value,
            proof_edges=tuple(self.minimum_verified_evidence_edge_view(edge) for edge in item.proof_edges),
            provenance=compact_provenance_views(item.provenance),
        )

    def minimum_verified_build_target_view(self, item: MinimumVerifiedBuildTarget) -> MinimumVerifiedBuildTargetView:
        return MinimumVerifiedBuildTargetView(
            action_id=item.target.action_id,
            name=item.target.name,
            provider_id=item.target.provider_id,
            target_id=item.target.target_id,
            target_kind=item.target.target_kind.value,
            owner_ids=item.target.owner_ids,
            invocation=self.minimum_verified_command_summary_view(
                item.target.invocation.argv,
                cwd=item.target.invocation.cwd,
            ),
            dry_run_supported=item.target.dry_run_supported,
            inclusion_reason=item.inclusion_reason,
            inclusion_confidence_mode=item.inclusion_confidence_mode.value,
            proof_edges=tuple(self.minimum_verified_evidence_edge_view(edge) for edge in item.proof_edges),
            provenance=compact_provenance_views(item.provenance),
        )

    def minimum_verified_runner_action_view(self, item: MinimumVerifiedRunnerAction) -> MinimumVerifiedRunnerActionView:
        return MinimumVerifiedRunnerActionView(
            action_id=item.action.id,
            name=item.action.name,
            provider_id=item.action.provider_id,
            target_id=item.action.target_id,
            target_kind=item.action.target_kind.value,
            invocation=self.minimum_verified_command_summary_view(
                item.action.invocation.argv,
                cwd=item.action.invocation.cwd,
            ),
            inclusion_reason=item.inclusion_reason,
            inclusion_confidence_mode=item.inclusion_confidence_mode.value,
            proof_edges=tuple(self.minimum_verified_evidence_edge_view(edge) for edge in item.proof_edges),
            provenance=compact_provenance_views(item.provenance),
        )

    def minimum_verified_quality_operation_view(
        self,
        item: MinimumVerifiedQualityOperation,
    ) -> MinimumVerifiedQualityOperationView:
        return MinimumVerifiedQualityOperationView(
            id=item.id,
            provider_id=item.provider_id,
            operation=item.operation.value,
            scope=item.scope.value,
            repository_rel_paths=item.repository_rel_paths,
            mcp_tool_name=item.mcp_tool_name,
            is_fix=item.is_fix,
            is_mutating=item.is_mutating,
            inclusion_reason=item.inclusion_reason,
            inclusion_confidence_mode=item.inclusion_confidence_mode.value,
            proof_edges=tuple(self.minimum_verified_evidence_edge_view(edge) for edge in item.proof_edges),
            provenance=compact_provenance_views(item.provenance),
        )

    def excluded_minimum_verified_item_view(
        self,
        item: ExcludedMinimumVerifiedItem,
    ) -> ExcludedMinimumVerifiedItemView:
        return ExcludedMinimumVerifiedItemView(
            item_kind=item.item_kind.value,
            item_id=item.item_id,
            reason_code=item.reason_code.value,
            reason=item.reason,
            replaced_by_ids=item.replaced_by_ids,
            provenance=compact_provenance_views(item.provenance),
        )

    def minimum_verified_change_set_view(
        self,
        change_set: MinimumVerifiedChangeSet,
    ) -> MinimumVerifiedChangeSetView:
        return MinimumVerifiedChangeSetView(
            target_kind=change_set.target_kind,
            owner=self._ownership_presenter.owner_view(change_set.owner),
            primary_component=(
                self._architecture_presenter.component_view(change_set.primary_component)
                if change_set.primary_component is not None
                else None
            ),
            tests=tuple(self.minimum_verified_test_target_view(item) for item in change_set.tests),
            build_targets=tuple(self.minimum_verified_build_target_view(item) for item in change_set.build_targets),
            runner_actions=tuple(self.minimum_verified_runner_action_view(item) for item in change_set.runner_actions),
            quality_validation_operations=tuple(
                self.minimum_verified_quality_operation_view(item)
                for item in change_set.quality_validation_operations
            ),
            quality_hygiene_operations=tuple(
                self.minimum_verified_quality_operation_view(item)
                for item in change_set.quality_hygiene_operations
            ),
            excluded_items=tuple(
                self.excluded_minimum_verified_item_view(item)
                for item in change_set.excluded_items
            ),
            provenance=compact_provenance_views(change_set.provenance),
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
            component_context=None,
            file_context=None,
            symbol_context=None,
            dependent_components=tuple(
                self._architecture_presenter.component_view(item) for item in impact.dependent_components
            ),
            reference_locations=tuple(self._code_presenter.location_view(item) for item in impact.reference_locations),
            related_tests=tuple(self.test_impact_view(item) for item in impact.related_tests),
            related_runners=tuple(self.runner_impact_view(item) for item in impact.related_runners),
            quality_gates=tuple(self.quality_gate_view(item) for item in impact.quality_gates),
            evidence=self.change_evidence_preview_view(impact.evidence),
            truth_coverage=self._intelligence_presenter.truth_coverage_summary_view(impact.truth_coverage),
            provenance=provenance_views(impact.provenance),
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
                provider_id: sorted_role_values(roles)
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
            truth_coverage=None,
            provenance=provenance_views(tuple(provenance_entries)),
        )
