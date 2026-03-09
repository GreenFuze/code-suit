from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.change_models import ChangeImpact, ChangeTarget, QualityGateInfo, RunnerImpact, TestImpact
from suitcode.core.change_evidence import ChangeEvidenceAssembler
from suitcode.core.code.models import CodeLocation
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.context_service import ContextService
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.impact_target_resolution import ImpactTargetResolver
from suitcode.core.intelligence_models import ComponentContext
from suitcode.core.models import Component, Runner
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, ownership_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, summarize_related_provenance
from suitcode.core.tests.models import ResolvedRelatedTest
from suitcode.core.truth_coverage_service import TruthCoverageService

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ChangeImpactService:
    def __init__(
        self,
        repository: Repository,
        ownership_index: OwnershipIndex,
        context_service: ContextService,
        component_context_resolver: ComponentContextResolver,
        code_reference_service: CodeReferenceService,
        truth_coverage_service: TruthCoverageService,
    ) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._component_context_resolver = component_context_resolver
        self._target_resolver = ImpactTargetResolver(
            repository,
            ownership_index,
            context_service,
            component_context_resolver,
            code_reference_service,
        )
        self._evidence_assembler = ChangeEvidenceAssembler()
        self._truth_coverage_service = truth_coverage_service

    def analyze_change(
        self,
        target: ChangeTarget,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        resolved = self._target_resolver.resolve(
            symbol_id=target.symbol_id,
            repository_rel_path=target.repository_rel_path,
            owner_id=target.owner_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        if resolved.target_kind == "symbol":
            return self._analyze_resolved_target(
                resolved,
                primary_component_id=resolved.file_primary_component_id,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
                runner_preview_limit=runner_preview_limit,
            )
        if resolved.target_kind == "file":
            return self._analyze_resolved_target(
                resolved,
                primary_component_id=resolved.file_primary_component_id,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
                runner_preview_limit=runner_preview_limit,
            )
        return self._analyze_resolved_target(
            resolved,
            primary_component_id=resolved.owner_primary_component_id,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
            runner_preview_limit=runner_preview_limit,
        )

    def _analyze_resolved_target(
        self,
        resolved,
        *,
        primary_component_id: str | None,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        primary_component = self._target_resolver.resolve_component(primary_component_id)
        component_context = self._primary_component_context(
            primary_component,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        dependent_components = self._dependent_components(primary_component, dependent_preview_limit)
        related_tests = self._test_impacts(resolved.related_tests)
        if resolved.target_kind == "owner":
            related_runners = self._related_runners_for_owner(resolved.owner.id, primary_component, runner_preview_limit)
            quality_gates = self._quality_gates_for_owner(resolved.owner.id)
        else:
            related_runners = self._related_runners_for_component(primary_component, runner_preview_limit)
            if resolved.evidence_path is None:
                raise ValueError("file and symbol targets must include evidence_path")
            quality_gates = self._quality_gates_for_path(resolved.evidence_path)
        dependent_edges = self._dependent_component_edges(primary_component, dependent_components)
        return ChangeImpact(
            target_kind=resolved.target_kind,
            owner=resolved.owner,
            primary_component=primary_component,
            component_context=component_context,
            file_context=resolved.file_context,
            symbol_context=resolved.symbol_context,
            dependent_components=dependent_components,
            reference_locations=resolved.reference_locations,
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
            evidence=self._evidence_assembler.assemble(
                target_kind=resolved.target_kind,
                target_value=self._target_value(resolved),
                evidence_path=resolved.evidence_path,
                owner=resolved.owner,
                primary_component=primary_component,
                reference_locations=resolved.reference_locations,
                dependent_components=dependent_components,
                dependent_edges=dependent_edges,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
            ),
            truth_coverage=self._truth_coverage_service.change_truth_coverage_from_parts(
                target_kind=resolved.target_kind,
                owner_id=resolved.owner.id,
                evidence_path=resolved.evidence_path,
                primary_component=primary_component,
                component_context=component_context,
                file_context=resolved.file_context,
                symbol_context=resolved.symbol_context,
                dependent_components=dependent_components,
                reference_locations=resolved.reference_locations,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
            ),
            provenance=self._change_provenance(
                owner_id=resolved.owner.id,
                dependent_components=dependent_components,
                reference_locations=resolved.reference_locations,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
                evidence_path=resolved.evidence_path,
            ),
        )

    def _primary_component_context(
        self,
        primary_component: Component | None,
        dependent_preview_limit: int,
        test_preview_limit: int,
    ) -> ComponentContext | None:
        if primary_component is None:
            return None
        return self._repository.describe_components(
            (primary_component.id,),
            file_preview_limit=20,
            dependency_preview_limit=20,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )[0]

    def _dependent_components(
        self,
        primary_component: Component | None,
        dependent_preview_limit: int,
    ) -> tuple[Component, ...]:
        if primary_component is None:
            return tuple()
        dependent_ids = self._repository.arch.get_component_dependents(primary_component.id)
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        resolved: list[Component] = []
        for component_id in dependent_ids[:dependent_preview_limit]:
            try:
                resolved.append(components_by_id[component_id])
            except KeyError as exc:
                raise ValueError(f"dependent component id could not be resolved: `{component_id}`") from exc
        return tuple(resolved)

    def _dependent_component_edges(
        self,
        primary_component: Component | None,
        dependent_components: tuple[Component, ...],
    ) -> tuple[ComponentDependencyEdge, ...]:
        if primary_component is None or not dependent_components:
            return tuple()
        dependent_ids = {component.id for component in dependent_components}
        return tuple(
            edge
            for edge in self._repository.arch.get_component_dependency_edges()
            if edge.target_kind == "component"
            and edge.target_id == primary_component.id
            and edge.source_component_id in dependent_ids
        )

    @staticmethod
    def _target_value(resolved) -> str:
        if resolved.target_kind == "symbol":
            if resolved.symbol_context is None:
                raise ValueError("symbol target requires symbol_context")
            return resolved.symbol_context.symbol.id
        if resolved.target_kind == "file":
            if resolved.evidence_path is None:
                raise ValueError("file target requires evidence_path")
            return resolved.evidence_path
        return resolved.owner.id

    def _test_impacts(self, related_tests: tuple[ResolvedRelatedTest, ...]) -> tuple[TestImpact, ...]:
        impacts: list[TestImpact] = []
        for related_test in related_tests:
            if related_test.matched_owner_id is not None:
                reason = "same_owner"
            elif related_test.matched_repository_rel_path is not None:
                reason = "same_file_context"
            else:
                reason = "related_test_scope"
            impacts.append(
                TestImpact(
                    related_test=related_test,
                    reason=reason,
                    provenance=related_test.provenance,
                )
            )
        return tuple(impacts)

    def _related_runners_for_component(
        self,
        primary_component: Component | None,
        runner_preview_limit: int,
    ) -> tuple[RunnerImpact, ...]:
        if primary_component is None:
            return tuple()
        owned_files = self._ownership_index.files_for_owner(primary_component.id)
        runner_ids = self._component_context_resolver.related_runner_ids_for_component(primary_component, owned_files)
        runners_by_id = {runner.id: runner for runner in self._repository.arch.get_runners()}
        impacts: list[RunnerImpact] = []
        for runner_id in runner_ids[:runner_preview_limit]:
            try:
                runner = runners_by_id[runner_id]
            except KeyError as exc:
                raise ValueError(f"runner id could not be resolved: `{runner_id}`") from exc
            impacts.append(
                RunnerImpact(
                    runner=runner,
                    reason="same_component",
                    provenance=(
                        ownership_provenance(
                            evidence_summary=f"runner `{runner.id}` linked to component `{primary_component.id}` through ownership context",
                            evidence_paths=merge_provenance_paths(runner.provenance, limit=10),
                        ),
                    ),
                )
            )
        return tuple(impacts)

    def _related_runners_for_owner(
        self,
        owner_id: str,
        primary_component: Component | None,
        runner_preview_limit: int,
    ) -> tuple[RunnerImpact, ...]:
        owner = self._ownership_index.owner_info(owner_id)
        if owner.kind == "runner":
            runners_by_id = {runner.id: runner for runner in self._repository.arch.get_runners()}
            try:
                runner = runners_by_id[owner_id]
            except KeyError as exc:
                raise ValueError(f"runner id could not be resolved: `{owner_id}`") from exc
            return (
                RunnerImpact(
                    runner=runner,
                    reason="same_owner",
                    provenance=(
                        ownership_provenance(
                            evidence_summary=f"runner impact anchored directly to runner owner `{owner_id}`",
                            evidence_paths=merge_provenance_paths(runner.provenance, limit=10),
                        ),
                    ),
                ),
            )
        if owner.kind in {"package_manager", "test_definition"}:
            return tuple()
        return self._related_runners_for_component(primary_component, runner_preview_limit)

    def _quality_gates_for_path(self, repository_rel_path: str) -> tuple[QualityGateInfo, ...]:
        return tuple(
            QualityGateInfo(
                provider_id=provider_id,
                provider_roles=("quality",),
                applies=True,
                reason="quality provider applies to the target file through repository quality support",
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.QUALITY_TOOL,
                        source_tool=provider_id,
                        evidence_summary=f"quality applicability derived for `{repository_rel_path}` through provider `{provider_id}`",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            )
            for provider_id in self._repository.quality.provider_ids
        )

    def _quality_gates_for_owner(self, owner_id: str) -> tuple[QualityGateInfo, ...]:
        owned_files = self._ownership_index.files_for_owner(owner_id)
        evidence_paths = tuple(file_info.repository_rel_path for file_info in owned_files[:10])
        applies = bool(owned_files)
        reason = (
            "quality provider applies through files owned by the target owner"
            if applies
            else "quality provider does not apply because the owner has no owned files"
        )
        return tuple(
            QualityGateInfo(
                provider_id=provider_id,
                provider_roles=("quality",),
                applies=applies,
                reason=reason,
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.QUALITY_TOOL,
                        source_tool=provider_id,
                        evidence_summary=f"quality applicability derived for owner `{owner_id}` through provider `{provider_id}`",
                        evidence_paths=evidence_paths,
                    ),
                ),
            )
            for provider_id in self._repository.quality.provider_ids
        )

    def _change_provenance(
        self,
        owner_id: str,
        dependent_components: tuple[Component, ...],
        reference_locations: tuple[CodeLocation, ...],
        related_tests: tuple[TestImpact, ...],
        related_runners: tuple[RunnerImpact, ...],
        quality_gates: tuple[QualityGateInfo, ...],
        evidence_path: str | None,
    ):
        entries = [
            ownership_provenance(
                evidence_summary=f"change analysis anchored to owner `{owner_id}`",
                evidence_paths=((evidence_path,) if evidence_path is not None else ()),
            )
        ]
        if dependent_components:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.MANIFEST,
                    evidence_summary=f"dependent component impact derived from {len(dependent_components)} dependency edges",
                    evidence_paths=merge_provenance_paths(
                        item for component in dependent_components for item in component.provenance
                    ),
                )
            )
        if reference_locations:
            entries.append(
                summarize_related_provenance(
                    (item for location in reference_locations for item in location.provenance),
                    "reference impact derived from LSP definition/reference results",
                )
            )
        if related_tests:
            entries.append(
                summarize_related_provenance(
                    (item for related_test in related_tests for item in related_test.provenance),
                    "related test impact derived from discovered test provenance",
                )
            )
        if related_runners:
            entries.append(
                summarize_related_provenance(
                    (item for runner in related_runners for item in runner.provenance),
                    "related runner impact derived from ownership and component context",
                )
            )
        if quality_gates:
            entries.append(
                summarize_related_provenance(
                    (item for gate in quality_gates for item in gate.provenance),
                    "quality gate applicability derived from repository quality providers",
                )
            )
        return tuple(entries)
