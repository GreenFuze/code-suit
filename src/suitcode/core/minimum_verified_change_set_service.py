from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.action_models import ActionKind, ActionQuery, ActionTargetKind, RepositoryAction
from suitcode.core.build_models import BuildTargetDescription
from suitcode.core.change_models import ChangeTarget
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.minimum_verified_change_set_models import (
    ExcludedMinimumVerifiedItem,
    MinimumVerifiedBuildTarget,
    MinimumVerifiedChangeSet,
    MinimumVerifiedEvidenceEdge,
    MinimumVerifiedEvidenceEdgeKind,
    MinimumVerifiedExclusionReason,
    MinimumVerifiedItemKind,
    MinimumVerifiedQualityOperation,
    MinimumVerifiedRunnerAction,
    MinimumVerifiedTestTarget,
    QualityOperationKind,
    QualityOperationScope,
)
from suitcode.core.models import Component, FileInfo
from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, ownership_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_confidence_mode
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import ResolvedRelatedTest, RelatedTestTarget, TestTargetDescription
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.structured_artifact_models import StructuredArtifact


@dataclass(frozen=True)
class _ResolvedMinimumTarget:
    target_kind: str
    target_anchor_id: str
    owner: OwnedNodeInfo
    primary_component: Component | None
    evidence_path: str | None
    relevant_files: tuple[str, ...]
    owner_files: tuple[FileInfo, ...]


@dataclass(frozen=True)
class _ResolvedTestCandidate:
    match: ResolvedRelatedTest
    description: TestTargetDescription
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]


@dataclass(frozen=True)
class _ResolvedBuildCandidate:
    target: BuildTargetDescription
    inclusion_reason: str
    inclusion_confidence_mode: ConfidenceMode
    proof_edges: tuple[MinimumVerifiedEvidenceEdge, ...]
    provenance: tuple[ProvenanceEntry, ...]
    selection_scope: str


@dataclass(frozen=True)
class _ResolvedDependentComponent:
    component: Component
    dependency_edges: tuple[ComponentDependencyEdge, ...]


class MinimumVerifiedQualityPlanner:
    def build_operations(
        self,
        *,
        target_anchor_id: str,
        provider_ids: tuple[str, ...],
        relevant_files: tuple[str, ...],
    ) -> tuple[tuple[MinimumVerifiedQualityOperation, ...], tuple[MinimumVerifiedQualityOperation, ...]]:
        validation_operations: list[MinimumVerifiedQualityOperation] = []
        hygiene_operations: list[MinimumVerifiedQualityOperation] = []
        for provider_id in provider_ids:
            lint_provenance = (
                derived_summary_provenance(
                    source_kind=SourceKind.QUALITY_TOOL,
                    source_tool=provider_id,
                    evidence_summary="non-mutating lint validation applies to the exact affected file set",
                    evidence_paths=relevant_files[:10],
                ),
            )
            format_provenance = (
                derived_summary_provenance(
                    source_kind=SourceKind.QUALITY_TOOL,
                    source_tool=provider_id,
                    evidence_summary="format hygiene applies to the exact affected file set",
                    evidence_paths=relevant_files[:10],
                ),
            )
            validation_operations.append(
                MinimumVerifiedQualityOperation(
                    id=f"quality_op:{provider_id}:lint",
                    provider_id=provider_id,
                    operation=QualityOperationKind.LINT,
                    scope=QualityOperationScope.VALIDATION,
                    repository_rel_paths=relevant_files,
                    mcp_tool_name="lint_file",
                    is_fix=False,
                    is_mutating=False,
                    inclusion_reason="non-mutating lint validation applies to the exact affected file set",
                    inclusion_confidence_mode=preferred_confidence_mode(lint_provenance),
                    proof_edges=(
                        MinimumVerifiedEvidenceEdge(
                            source_node_kind="change_target",
                            source_node_id=target_anchor_id,
                            target_node_kind="quality_operation",
                            target_node_id=f"quality_op:{provider_id}:lint",
                            edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_QUALITY_VALIDATION,
                            reason="non-mutating lint validation applies to the exact affected file set",
                            provenance=lint_provenance,
                        ),
                    ),
                    provenance=lint_provenance,
                )
            )
            hygiene_operations.append(
                MinimumVerifiedQualityOperation(
                    id=f"quality_op:{provider_id}:format",
                    provider_id=provider_id,
                    operation=QualityOperationKind.FORMAT,
                    scope=QualityOperationScope.HYGIENE,
                    repository_rel_paths=relevant_files,
                    mcp_tool_name="format_file",
                    is_fix=None,
                    is_mutating=True,
                    inclusion_reason="format hygiene applies to the exact affected file set",
                    inclusion_confidence_mode=preferred_confidence_mode(format_provenance),
                    proof_edges=(
                        MinimumVerifiedEvidenceEdge(
                            source_node_kind="change_target",
                            source_node_id=target_anchor_id,
                            target_node_kind="quality_operation",
                            target_node_id=f"quality_op:{provider_id}:format",
                            edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_QUALITY_HYGIENE,
                            reason="format hygiene applies to the exact affected file set",
                            provenance=format_provenance,
                        ),
                    ),
                    provenance=format_provenance,
                )
            )
        return tuple(validation_operations), tuple(hygiene_operations)


class MinimumVerifiedCandidateResolver:
    def __init__(self, repository: Repository, component_context_resolver: ComponentContextResolver) -> None:
        self._repository = repository
        self._component_context_resolver = component_context_resolver

    def resolve_target(self, target: ChangeTarget) -> _ResolvedMinimumTarget:
        if target.repository_rel_path is not None:
            file_owner = self._repository.get_file_owner(target.repository_rel_path)
            owner = file_owner.owner
            evidence_path = file_owner.file_info.repository_rel_path
            primary_component = self._primary_component_for_file(evidence_path, owner.id)
            owner_files = self._repository.list_files_by_owner(owner.id)
            return _ResolvedMinimumTarget(
                target_kind="file",
                target_anchor_id=f"change_target:file:{evidence_path}",
                owner=owner,
                primary_component=primary_component,
                evidence_path=evidence_path,
                relevant_files=(evidence_path,),
                owner_files=owner_files,
            )

        if target.symbol_id is not None:
            symbol_context = self._repository.describe_symbol_context(target.symbol_id, reference_preview_limit=1, test_preview_limit=1)
            owner = symbol_context.owner
            evidence_path = symbol_context.symbol.path
            primary_component = self._primary_component_for_file(evidence_path, owner.id)
            owner_files = self._repository.list_files_by_owner(owner.id)
            return _ResolvedMinimumTarget(
                target_kind="symbol",
                target_anchor_id=f"change_target:symbol:{target.symbol_id}",
                owner=owner,
                primary_component=primary_component,
                evidence_path=evidence_path,
                relevant_files=(evidence_path,),
                owner_files=owner_files,
            )

        assert target.owner_id is not None
        owner = self._repository.resolve_owner(target.owner_id)
        owner_files = self._repository.list_files_by_owner(owner.id)
        relevant_files = tuple(sorted({item.repository_rel_path for item in owner_files}))
        primary_component = self._primary_component_for_owner(owner.id)
        return _ResolvedMinimumTarget(
            target_kind="owner",
            target_anchor_id=f"change_target:owner:{owner.id}",
            owner=owner,
            primary_component=primary_component,
            evidence_path=None,
            relevant_files=relevant_files,
            owner_files=owner_files,
        )

    def related_tests(self, resolved: _ResolvedMinimumTarget) -> tuple[ResolvedRelatedTest, ...]:
        if resolved.target_kind == "owner":
            return self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=resolved.owner.id))
        assert resolved.evidence_path is not None
        return self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=resolved.evidence_path))

    def build_targets(self) -> tuple[BuildTargetDescription, ...]:
        return self._repository.list_build_targets()

    def runner_actions(self, owner_id: str) -> tuple[RepositoryAction, ...]:
        return self._repository.list_actions(
            ActionQuery(
                runner_id=owner_id,
                action_kinds=(ActionKind.RUNNER_EXECUTION,),
            )
        )

    def related_runner_ids(self, resolved: _ResolvedMinimumTarget) -> tuple[str, ...]:
        if resolved.primary_component is None:
            return tuple()
        return self._component_context_resolver.related_runner_ids_for_component(
            resolved.primary_component,
            resolved.owner_files,
        )

    def direct_dependent_components(self, resolved: _ResolvedMinimumTarget) -> tuple[_ResolvedDependentComponent, ...]:
        if resolved.primary_component is None:
            return tuple()
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        dependent_components: list[_ResolvedDependentComponent] = []
        for dependent_id in self._repository.arch.get_component_dependents(resolved.primary_component.id):
            component = components_by_id.get(dependent_id)
            if component is None:
                continue
            dependency_edges = tuple(
                edge
                for edge in self._repository.arch.get_component_dependency_edges(dependent_id)
                if edge.target_kind == "component" and edge.target_id == resolved.primary_component.id
            )
            if not dependency_edges:
                continue
            dependent_components.append(
                _ResolvedDependentComponent(
                    component=component,
                    dependency_edges=dependency_edges,
                )
            )
        return tuple(sorted(dependent_components, key=lambda item: item.component.id))

    def related_tests_for_dependent_components(
        self,
        dependents: tuple[_ResolvedDependentComponent, ...],
    ) -> tuple[tuple[ResolvedRelatedTest, tuple[ProvenanceEntry, ...]], ...]:
        candidates: list[tuple[ResolvedRelatedTest, tuple[ProvenanceEntry, ...]]] = []
        seen_test_ids: set[str] = set()
        for dependent in dependents:
            related = self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=dependent.component.id))
            dependency_provenance = self._merge_provenance(*(edge.provenance for edge in dependent.dependency_edges))
            for item in related:
                if item.test_definition.id in seen_test_ids:
                    continue
                seen_test_ids.add(item.test_definition.id)
                candidates.append(
                    (
                        ResolvedRelatedTest(
                            match=RelatedTestMatch(
                                test_definition=item.test_definition,
                                relation_reason="dependent_component",
                                matched_owner_id=dependent.component.id,
                            ),
                            discovered_test=DiscoveredTestDefinition(
                                test_definition=item.discovered_test.test_definition,
                                provenance=item.discovered_test.provenance,
                            ),
                        ),
                        dependency_provenance,
                    )
                )
        return tuple(candidates)

    @staticmethod
    def _merge_provenance(*groups: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceEntry, ...]:
        merged: list[ProvenanceEntry] = []
        for group in groups:
            for entry in group:
                if entry not in merged:
                    merged.append(entry)
        return tuple(merged)

    def _primary_component_for_file(self, repository_rel_path: str, owner_id: str) -> Component | None:
        component_id = self._component_context_resolver.primary_component_id_for_file(repository_rel_path, owner_id)
        return self._component_by_id(component_id)

    def _primary_component_for_owner(self, owner_id: str) -> Component | None:
        component_id = self._component_context_resolver.primary_component_id_for_owner(owner_id)
        return self._component_by_id(component_id)

    def _component_by_id(self, component_id: str | None) -> Component | None:
        if component_id is None:
            return None
        for component in self._repository.arch.get_components():
            if component.id == component_id:
                return component
        raise ValueError(f"resolved primary component does not exist: `{component_id}`")


class MinimumVerifiedEvidenceAssembler:
    def test_item(
        self,
        *,
        target_anchor_id: str,
        match: ResolvedRelatedTest,
        description: TestTargetDescription,
        inclusion_reason: str,
    ) -> MinimumVerifiedTestTarget:
        provenance = self._merged_provenance(match.provenance, description.provenance)
        proof = (
            MinimumVerifiedEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_anchor_id,
                target_node_kind="test_target",
                target_node_id=description.test_definition.id,
                edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_TEST_TARGET,
                reason=inclusion_reason,
                provenance=match.provenance,
            ),
        )
        return MinimumVerifiedTestTarget(
            target=description,
            inclusion_reason=inclusion_reason,
            inclusion_confidence_mode=preferred_confidence_mode(provenance),
            proof_edges=proof,
            provenance=provenance,
        )

    def build_item(
        self,
        *,
        source_node_kind: str,
        source_node_id: str,
        target: BuildTargetDescription,
        inclusion_reason: str,
        edge_kind: MinimumVerifiedEvidenceEdgeKind,
    ) -> MinimumVerifiedBuildTarget:
        proof = (
            MinimumVerifiedEvidenceEdge(
                source_node_kind=source_node_kind,
                source_node_id=source_node_id,
                target_node_kind="build_target",
                target_node_id=target.action_id,
                edge_kind=edge_kind,
                reason=inclusion_reason,
                provenance=target.provenance,
            ),
        )
        return MinimumVerifiedBuildTarget(
            target=target,
            inclusion_reason=inclusion_reason,
            inclusion_confidence_mode=preferred_confidence_mode(target.provenance),
            proof_edges=proof,
            provenance=target.provenance,
        )

    def dependent_test_item(
        self,
        *,
        target_anchor_id: str,
        match: ResolvedRelatedTest,
        description: TestTargetDescription,
        dependency_provenance: tuple[ProvenanceEntry, ...],
        inclusion_reason: str,
    ) -> MinimumVerifiedTestTarget:
        proof_provenance = self._merged_provenance(dependency_provenance, match.provenance, description.provenance)
        proof = (
            MinimumVerifiedEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_anchor_id,
                target_node_kind="test_target",
                target_node_id=description.test_definition.id,
                edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_TEST_TARGET,
                reason=inclusion_reason,
                provenance=proof_provenance,
            ),
        )
        return MinimumVerifiedTestTarget(
            target=description,
            inclusion_reason=inclusion_reason,
            inclusion_confidence_mode=preferred_confidence_mode(proof_provenance),
            proof_edges=proof,
            provenance=proof_provenance,
        )

    def dependent_build_item(
        self,
        *,
        source_component_id: str,
        target: BuildTargetDescription,
        dependency_provenance: tuple[ProvenanceEntry, ...],
        inclusion_reason: str,
    ) -> MinimumVerifiedBuildTarget:
        proof_provenance = self._merged_provenance(dependency_provenance, target.provenance)
        proof = (
            MinimumVerifiedEvidenceEdge(
                source_node_kind="component",
                source_node_id=source_component_id,
                target_node_kind="build_target",
                target_node_id=target.action_id,
                edge_kind=MinimumVerifiedEvidenceEdgeKind.COMPONENT_BUILD_TARGET,
                reason=inclusion_reason,
                provenance=proof_provenance,
            ),
        )
        return MinimumVerifiedBuildTarget(
            target=target,
            inclusion_reason=inclusion_reason,
            inclusion_confidence_mode=preferred_confidence_mode(proof_provenance),
            proof_edges=proof,
            provenance=proof_provenance,
        )

    def runner_item(
        self,
        *,
        owner_id: str,
        action: RepositoryAction,
    ) -> MinimumVerifiedRunnerAction:
        inclusion_reason = "target is directly owned by this runner"
        proof = (
            MinimumVerifiedEvidenceEdge(
                source_node_kind="owner",
                source_node_id=owner_id,
                target_node_kind="runner_action",
                target_node_id=action.id,
                edge_kind=MinimumVerifiedEvidenceEdgeKind.TARGET_RUNNER_ACTION,
                reason=inclusion_reason,
                provenance=action.provenance,
            ),
        )
        return MinimumVerifiedRunnerAction(
            action=action,
            inclusion_reason=inclusion_reason,
            inclusion_confidence_mode=preferred_confidence_mode(action.provenance),
            proof_edges=proof,
            provenance=action.provenance,
        )

    @staticmethod
    def exclusion(
        *,
        item_kind: MinimumVerifiedItemKind,
        item_id: str,
        reason_code: MinimumVerifiedExclusionReason,
        reason: str,
        provenance: tuple[ProvenanceEntry, ...],
        replaced_by_ids: tuple[str, ...] = (),
    ) -> ExcludedMinimumVerifiedItem:
        return ExcludedMinimumVerifiedItem(
            item_kind=item_kind,
            item_id=item_id,
            reason_code=reason_code,
            reason=reason,
            replaced_by_ids=replaced_by_ids,
            provenance=provenance,
        )

    @staticmethod
    def _merged_provenance(*groups: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceEntry, ...]:
        merged: list[ProvenanceEntry] = []
        for group in groups:
            for entry in group:
                if entry not in merged:
                    merged.append(entry)
        return tuple(merged)


class MinimumVerifiedMinimizer:
    def __init__(
        self,
        repository: Repository,
        evidence_assembler: MinimumVerifiedEvidenceAssembler,
    ) -> None:
        self._repository = repository
        self._evidence_assembler = evidence_assembler

    def minimize_tests(
        self,
        *,
        target_anchor_id: str,
        matches: tuple[ResolvedRelatedTest, ...],
    ) -> tuple[tuple[MinimumVerifiedTestTarget, ...], tuple[ExcludedMinimumVerifiedItem, ...]]:
        grouped: dict[str, list[ResolvedRelatedTest]] = {}
        for match in matches:
            grouped.setdefault(match.test_definition.id, []).append(match)

        included: list[MinimumVerifiedTestTarget] = []
        exclusions: list[ExcludedMinimumVerifiedItem] = []

        for test_id in sorted(grouped):
            candidates = grouped[test_id]
            selected = sorted(candidates, key=self._test_match_sort_key)[0]
            for candidate in candidates:
                if candidate is selected:
                    continue
                exclusions.append(
                    self._evidence_assembler.exclusion(
                        item_kind=MinimumVerifiedItemKind.TEST_TARGET,
                        item_id=test_id,
                        reason_code=MinimumVerifiedExclusionReason.DUPLICATE_REPLACED_BY_STRONGER_MATCH,
                        reason="weaker duplicate test match replaced by stronger deterministic match",
                        replaced_by_ids=(test_id,),
                        provenance=candidate.provenance,
                    )
                )
            description = self._repository.describe_test_target(test_id)
            included.append(
                self._evidence_assembler.test_item(
                    target_anchor_id=target_anchor_id,
                    match=selected,
                    description=description,
                    inclusion_reason=self._human_test_reason(selected),
                )
            )

        has_specific = any(
            item.target.test_definition.id
            and any(
                candidate.test_definition.id == item.target.test_definition.id
                and (
                    candidate.matched_repository_rel_path is not None
                    or candidate.matched_owner_id is not None
                )
                for candidate in matches
            )
            for item in included
        )
        if not has_specific:
            return tuple(included), tuple(exclusions)

        kept: list[MinimumVerifiedTestTarget] = []
        for item in included:
            selected_match = next(candidate for candidate in matches if candidate.test_definition.id == item.target.test_definition.id and self._human_test_reason(candidate) == item.inclusion_reason)
            if selected_match.matched_repository_rel_path is None and selected_match.matched_owner_id is None:
                exclusions.append(
                    self._evidence_assembler.exclusion(
                        item_kind=MinimumVerifiedItemKind.TEST_TARGET,
                        item_id=item.target.test_definition.id,
                        reason_code=MinimumVerifiedExclusionReason.BROAD_TEST_REPLACED_BY_SPECIFIC_TESTS,
                        reason="broad fallback suite replaced by more specific related tests",
                        replaced_by_ids=tuple(sorted(candidate.target.test_definition.id for candidate in included if candidate is not item)),
                        provenance=item.provenance,
                    )
                )
                continue
            kept.append(item)
        return tuple(kept), tuple(exclusions)

    def minimize_build_targets(
        self,
        *,
        owner: OwnedNodeInfo,
        primary_component: Component | None,
        targets: tuple[BuildTargetDescription, ...],
        dependent_components: tuple[_ResolvedDependentComponent, ...] = tuple(),
    ) -> tuple[tuple[MinimumVerifiedBuildTarget, ...], tuple[ExcludedMinimumVerifiedItem, ...]]:
        component_targets = tuple(
            target
            for target in targets
            if primary_component is not None
            and target.target_kind == ActionTargetKind.COMPONENT
            and target.target_id == primary_component.id
        )
        owner_targets = tuple(
            target
            for target in targets
            if target.target_kind == ActionTargetKind.COMPONENT
            and (owner.id in target.owner_ids or (primary_component is not None and primary_component.id in target.owner_ids))
        )
        repository_targets = tuple(
            target for target in targets if target.target_kind == ActionTargetKind.REPOSITORY
        )

        exclusions: list[ExcludedMinimumVerifiedItem] = []
        if component_targets:
            included_targets = component_targets
            for target in repository_targets:
                exclusions.append(
                    self._evidence_assembler.exclusion(
                        item_kind=MinimumVerifiedItemKind.BUILD_TARGET,
                        item_id=target.action_id,
                        reason_code=MinimumVerifiedExclusionReason.REPOSITORY_BUILD_REPLACED_BY_NARROWER_BUILD,
                        reason="repository-wide build target replaced by narrower component-scoped build target",
                        replaced_by_ids=tuple(item.action_id for item in component_targets),
                        provenance=target.provenance,
                    )
                )
            return (
                tuple(
                    self._evidence_assembler.build_item(
                        source_node_kind="component",
                        source_node_id=primary_component.id,
                        target=target,
                        inclusion_reason="component-scoped build target is the narrowest deterministic build surface",
                        edge_kind=MinimumVerifiedEvidenceEdgeKind.COMPONENT_BUILD_TARGET,
                    )
                    for target in component_targets
                ),
                tuple(exclusions),
            )

        narrow_owner_targets = tuple(sorted({target.action_id: target for target in owner_targets}.values(), key=lambda item: item.action_id))
        if narrow_owner_targets:
            for target in repository_targets:
                exclusions.append(
                    self._evidence_assembler.exclusion(
                        item_kind=MinimumVerifiedItemKind.BUILD_TARGET,
                        item_id=target.action_id,
                        reason_code=MinimumVerifiedExclusionReason.REPOSITORY_BUILD_REPLACED_BY_NARROWER_BUILD,
                        reason="repository-wide build target replaced by narrower owner-associated build target",
                        replaced_by_ids=tuple(item.action_id for item in narrow_owner_targets),
                        provenance=target.provenance,
                    )
                )
            return (
                tuple(
                    self._evidence_assembler.build_item(
                        source_node_kind="owner",
                        source_node_id=owner.id,
                        target=target,
                        inclusion_reason="owner-associated build target is the narrowest deterministic build surface",
                        edge_kind=MinimumVerifiedEvidenceEdgeKind.OWNER_BUILD_TARGET,
                    )
                    for target in narrow_owner_targets
                ),
                tuple(exclusions),
            )

        dependent_component_targets: list[tuple[_ResolvedDependentComponent, BuildTargetDescription]] = []
        for dependent in dependent_components:
            for target in targets:
                if target.target_kind == ActionTargetKind.COMPONENT and target.target_id == dependent.component.id:
                    dependent_component_targets.append((dependent, target))
        if dependent_component_targets and primary_component is not None:
            deduped: dict[str, tuple[_ResolvedDependentComponent, BuildTargetDescription]] = {}
            for dependent, target in sorted(dependent_component_targets, key=lambda item: item[1].action_id):
                deduped.setdefault(target.action_id, (dependent, target))
            included = tuple(
                self._evidence_assembler.dependent_build_item(
                    source_component_id=primary_component.id,
                    target=target,
                    dependency_provenance=MinimumVerifiedEvidenceAssembler._merged_provenance(
                        *(edge.provenance for edge in dependent.dependency_edges)
                    ),
                    inclusion_reason="directly dependent buildable component is the narrowest deterministic build surface",
                )
                for dependent, target in deduped.values()
            )
            return included, tuple(exclusions)

        return (
            tuple(
                self._evidence_assembler.build_item(
                    source_node_kind="owner",
                    source_node_id=owner.id,
                    target=target,
                    inclusion_reason="repository-wide build target is the only deterministic build surface",
                    edge_kind=MinimumVerifiedEvidenceEdgeKind.OWNER_BUILD_TARGET,
                )
                for target in repository_targets
            ),
            tuple(),
        )

    def runner_items(
        self,
        *,
        owner: OwnedNodeInfo,
        actions: tuple[RepositoryAction, ...],
    ) -> tuple[MinimumVerifiedRunnerAction, ...]:
        if len(actions) != 1:
            raise ValueError(f"runner owner `{owner.id}` must resolve to exactly one runner execution action")
        return (self._evidence_assembler.runner_item(owner_id=owner.id, action=actions[0]),)

    @staticmethod
    def _test_match_sort_key(match: ResolvedRelatedTest) -> tuple[int, int, str, str]:
        specificity_rank = 0
        if match.matched_repository_rel_path is not None:
            specificity_rank = 0
        elif match.matched_owner_id is not None:
            specificity_rank = 1
        else:
            specificity_rank = 2
        confidence_rank = 0 if match.is_authoritative else 1
        return (
            specificity_rank,
            confidence_rank,
            match.relation_reason,
            match.matched_repository_rel_path or match.matched_owner_id or "",
        )

    @staticmethod
    def _human_test_reason(match: ResolvedRelatedTest) -> str:
        if match.matched_repository_rel_path is not None:
            return "exact file-related test"
        if match.relation_reason == "dependent_component":
            return "direct dependent component test"
        if match.matched_owner_id is not None:
            return "same owner/component test"
        return "broad fallback test suite"


class MinimumVerifiedChangeSetService:
    def __init__(
        self,
        repository: Repository,
        component_context_resolver: ComponentContextResolver,
    ) -> None:
        self._repository = repository
        self._candidate_resolver = MinimumVerifiedCandidateResolver(repository, component_context_resolver)
        self._evidence_assembler = MinimumVerifiedEvidenceAssembler()
        self._minimizer = MinimumVerifiedMinimizer(repository, self._evidence_assembler)
        self._quality_planner = MinimumVerifiedQualityPlanner()

    def get_minimum_verified_change_set(self, target: ChangeTarget) -> MinimumVerifiedChangeSet:
        resolved = self._candidate_resolver.resolve_target(target)
        artifact_member = self._artifact_member_for_target(resolved)
        structured_artifacts = self._structured_artifacts_for_target(resolved)
        dependent_components = (
            tuple()
            if structured_artifacts or artifact_member is not None
            else self._candidate_resolver.direct_dependent_components(resolved)
        )

        related_tests = tuple() if artifact_member is not None else self._candidate_resolver.related_tests(resolved)
        tests, test_exclusions = self._minimizer.minimize_tests(
            target_anchor_id=resolved.target_anchor_id,
            matches=related_tests,
        )

        if artifact_member is not None:
            build_targets = tuple()
            build_exclusions = tuple()
        else:
            build_targets, build_exclusions = self._minimizer.minimize_build_targets(
                owner=resolved.owner,
                primary_component=resolved.primary_component,
                targets=self._candidate_resolver.build_targets(),
                dependent_components=tuple(),
            )
        dependent_test_exclusions: list[ExcludedMinimumVerifiedItem] = []
        if not tests and dependent_components:
            dependent_matches = self._candidate_resolver.related_tests_for_dependent_components(dependent_components)
            if dependent_matches and build_targets:
                replacement_ids = tuple(item.target.action_id for item in build_targets)
                for match, dependency_provenance in dependent_matches:
                    dependent_test_exclusions.append(
                        self._evidence_assembler.exclusion(
                            item_kind=MinimumVerifiedItemKind.TEST_TARGET,
                            item_id=match.test_definition.id,
                            reason_code=MinimumVerifiedExclusionReason.DEPENDENT_TEST_REPLACED_BY_NARROWER_BUILD,
                            reason="direct dependent component test replaced by narrower deterministic build surface",
                            replaced_by_ids=replacement_ids,
                            provenance=MinimumVerifiedEvidenceAssembler._merged_provenance(
                                dependency_provenance,
                                match.provenance,
                            ),
                        )
                    )
            elif dependent_matches:
                tests = tuple(
                    self._evidence_assembler.dependent_test_item(
                        target_anchor_id=resolved.target_anchor_id,
                        match=match,
                        description=self._repository.describe_test_target(match.test_definition.id),
                        dependency_provenance=dependency_provenance,
                        inclusion_reason=self._minimizer._human_test_reason(match),
                    )
                    for match, dependency_provenance in dependent_matches
                )
        if artifact_member is None and not tests and not build_targets and dependent_components:
            build_targets, build_exclusions = self._minimizer.minimize_build_targets(
                owner=resolved.owner,
                primary_component=resolved.primary_component,
                targets=self._candidate_resolver.build_targets(),
                dependent_components=dependent_components,
            )

        runner_actions: tuple[MinimumVerifiedRunnerAction, ...] = tuple()
        if resolved.owner.kind == "runner":
            runner_actions = self._minimizer.runner_items(
                owner=resolved.owner,
                actions=self._candidate_resolver.runner_actions(resolved.owner.id),
            )

        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...] = tuple()
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...] = tuple()
        if resolved.relevant_files and artifact_member is None:
            quality_provider_ids = self._repository.quality.provider_ids_for_files(resolved.relevant_files)
            quality_validation_operations, quality_hygiene_operations = self._quality_planner.build_operations(
                target_anchor_id=resolved.target_anchor_id,
                provider_ids=quality_provider_ids,
                relevant_files=resolved.relevant_files,
            )

        availability_exclusions = self._availability_exclusions(
            resolved=resolved,
            artifact_member=artifact_member,
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
        )
        breadth_explanations = self._shared_file_surface_explanations(
            resolved=resolved,
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
        )

        provenance = self._overall_provenance(
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
            has_exclusions=bool(
                test_exclusions
                or dependent_test_exclusions
                or build_exclusions
                or breadth_explanations
                or availability_exclusions
            ),
        )

        self._validate_non_empty_change_set(
            resolved=resolved,
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
            availability_exclusions=availability_exclusions,
        )

        return MinimumVerifiedChangeSet(
            target_kind=resolved.target_kind,
            owner=resolved.owner,
            primary_component=resolved.primary_component,
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
            excluded_items=tuple(
                (
                    *test_exclusions,
                    *dependent_test_exclusions,
                    *build_exclusions,
                    *breadth_explanations,
                    *availability_exclusions,
                )
            ),
            provenance=provenance,
        )

    def _overall_provenance(
        self,
        *,
        tests: tuple[MinimumVerifiedTestTarget, ...],
        build_targets: tuple[MinimumVerifiedBuildTarget, ...],
        runner_actions: tuple[MinimumVerifiedRunnerAction, ...],
        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...],
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...],
        has_exclusions: bool,
    ) -> tuple[ProvenanceEntry, ...]:
        merged: list[ProvenanceEntry] = []
        for item in (*tests, *build_targets, *runner_actions, *quality_validation_operations, *quality_hygiene_operations):
            for entry in item.provenance:
                if entry not in merged:
                    merged.append(entry)
        if has_exclusions:
            merged.append(
                derived_summary_provenance(
                    source_kind=SourceKind.OWNERSHIP,
                    evidence_summary="minimum verified change set excludes supersets and weaker candidates deterministically",
                    evidence_paths=merge_provenance_paths(tuple(merged))[:10] if merged else tuple(),
                )
            )
        return tuple(merged)

    def _validate_non_empty_change_set(
        self,
        *,
        resolved: _ResolvedMinimumTarget,
        tests: tuple[MinimumVerifiedTestTarget, ...],
        build_targets: tuple[MinimumVerifiedBuildTarget, ...],
        runner_actions: tuple[MinimumVerifiedRunnerAction, ...],
        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...],
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...],
        availability_exclusions: tuple[ExcludedMinimumVerifiedItem, ...],
    ) -> None:
        if any(
            (
                tests,
                build_targets,
                runner_actions,
                quality_validation_operations,
                quality_hygiene_operations,
            )
        ):
            return
        if availability_exclusions:
            return
        target_descriptor = resolved.evidence_path or resolved.owner.id
        raise ValueError(
            "no deterministic validation surfaces were found for "
            f"{resolved.target_kind} target `{target_descriptor}`"
        )

    def _availability_exclusions(
        self,
        *,
        resolved: _ResolvedMinimumTarget,
        artifact_member: tuple[str, str] | None,
        tests: tuple[MinimumVerifiedTestTarget, ...],
        build_targets: tuple[MinimumVerifiedBuildTarget, ...],
        runner_actions: tuple[MinimumVerifiedRunnerAction, ...],
        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...],
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...],
    ) -> tuple[ExcludedMinimumVerifiedItem, ...]:
        if artifact_member is not None:
            evidence_paths = resolved.relevant_files[:10] or ((resolved.evidence_path,) if resolved.evidence_path is not None else tuple())
            owner_component_id, artifact_root = artifact_member
            return (
                self._evidence_assembler.exclusion(
                    item_kind=MinimumVerifiedItemKind.VALIDATION_SURFACE,
                    item_id=f"validation_surface:artifact:{resolved.evidence_path or resolved.owner.id}",
                    reason_code=MinimumVerifiedExclusionReason.NO_DETERMINISTIC_VALIDATION_SURFACE_FOR_ARTIFACT_MEMBER,
                    reason=(
                        "target is an explicit owned artifact member under "
                        f"`{artifact_root}` for component `{owner_component_id}` and no narrower deterministic validation surface is available"
                    ),
                    provenance=(
                        derived_summary_provenance(
                            source_kind=SourceKind.OWNERSHIP,
                            evidence_summary="explicit artifact member target has no inherited deterministic source validation surface",
                            evidence_paths=evidence_paths,
                        ),
                    ),
                ),
            )
        structured_artifacts = self._structured_artifacts_for_target(resolved)
        if structured_artifacts:
            evidence_paths = resolved.relevant_files[:10] or ((resolved.evidence_path,) if resolved.evidence_path is not None else tuple())
            artifact_labels = tuple(sorted({artifact.artifact_kind.value for artifact in structured_artifacts}))
            if len(artifact_labels) == 1:
                artifact_label = artifact_labels[0]
            else:
                artifact_label = ", ".join(artifact_labels)
            return (
                self._evidence_assembler.exclusion(
                    item_kind=MinimumVerifiedItemKind.VALIDATION_SURFACE,
                    item_id=f"validation_surface:{resolved.evidence_path or resolved.owner.id}",
                    reason_code=MinimumVerifiedExclusionReason.NO_DETERMINISTIC_VALIDATION_SURFACES_FOR_PROVIDER_OWNED_ARTIFACT,
                    reason=(
                        "target is provider-owned structured artifact content and exposes no deterministic validation surface; "
                        f"supported artifact kinds: {artifact_label}"
                    ),
                    provenance=(
                        derived_summary_provenance(
                            source_kind=SourceKind.DOCUMENT,
                            source_tool="structured_artifact",
                            evidence_summary="provider-owned structured artifact target has no deterministic validation surface",
                            evidence_paths=evidence_paths,
                        ),
                    ),
                ),
            )
        if tests:
            return tuple()
        remaining_surfaces: list[str] = []
        if build_targets:
            remaining_surfaces.append("build")
        if runner_actions:
            remaining_surfaces.append("runner")
        if quality_validation_operations or quality_hygiene_operations:
            remaining_surfaces.append("quality")
        if not remaining_surfaces:
            return tuple()
        evidence_paths = resolved.relevant_files[:10] or ((resolved.evidence_path,) if resolved.evidence_path is not None else tuple())
        if self._is_frontend_build_primary_surface(
            resolved=resolved,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
        ):
            reason = (
                "no finer deterministic frontend test target was discovered for this target; "
                "build is the primary deterministic frontend validation surface currently available"
            )
        elif len(remaining_surfaces) == 1:
            reason = (
                "no deterministic test targets were discovered for this target; "
                f"{remaining_surfaces[0]} surface is the only deterministic validation available"
            )
        elif len(remaining_surfaces) == 2:
            reason = (
                "no deterministic test targets were discovered for this target; "
                f"{remaining_surfaces[0]} and {remaining_surfaces[1]} surfaces are the only deterministic validation available"
            )
        else:
            reason = (
                "no deterministic test targets were discovered for this target; "
                f"{', '.join(remaining_surfaces[:-1])}, and {remaining_surfaces[-1]} surfaces are the only deterministic validation available"
            )
        return (
            self._evidence_assembler.exclusion(
                item_kind=MinimumVerifiedItemKind.TEST_TARGET,
                item_id=f"test_surface:{resolved.owner.id}",
                reason_code=MinimumVerifiedExclusionReason.NO_DETERMINISTIC_TEST_TARGETS_AVAILABLE,
                reason=reason,
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.OWNERSHIP,
                        evidence_summary="absence of deterministic test targets established from provider-owned validation surfaces",
                        evidence_paths=evidence_paths,
                    ),
                ),
            ),
        )

    @staticmethod
    def _is_frontend_source_path(repository_rel_path: str) -> bool:
        normalized = repository_rel_path.replace("\\", "/").lower()
        return normalized.endswith((".tsx", ".jsx", ".ts", ".js", ".mts", ".cts", ".mjs", ".cjs"))

    def _is_frontend_build_primary_surface(
        self,
        *,
        resolved: _ResolvedMinimumTarget,
        build_targets: tuple[MinimumVerifiedBuildTarget, ...],
        runner_actions: tuple[MinimumVerifiedRunnerAction, ...],
        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...],
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...],
    ) -> bool:
        if not build_targets or runner_actions:
            return False
        if any(item.target.provider_id != "npm" for item in build_targets):
            return False
        if any(item.provider_id != "npm" for item in quality_validation_operations):
            return False
        if any(item.provider_id != "npm" for item in quality_hygiene_operations):
            return False
        if not resolved.relevant_files:
            return False
        return all(self._is_frontend_source_path(path) for path in resolved.relevant_files)

    def _shared_file_surface_explanations(
        self,
        *,
        resolved: _ResolvedMinimumTarget,
        tests: tuple[MinimumVerifiedTestTarget, ...],
        build_targets: tuple[MinimumVerifiedBuildTarget, ...],
        runner_actions: tuple[MinimumVerifiedRunnerAction, ...],
        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...],
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...],
    ) -> tuple[ExcludedMinimumVerifiedItem, ...]:
        if resolved.target_kind != "file":
            return tuple()
        if runner_actions or quality_validation_operations or quality_hygiene_operations:
            return tuple()
        if not tests and not build_targets:
            return tuple()
        dependent_test_reasons = {
            "direct dependent component test",
        }
        dependent_build_reasons = {
            "directly dependent buildable component is the narrowest deterministic build surface",
        }
        tests_are_dependent = bool(tests) and all(item.inclusion_reason in dependent_test_reasons for item in tests)
        builds_are_dependent = bool(build_targets) and all(item.inclusion_reason in dependent_build_reasons for item in build_targets)
        if any(item.inclusion_reason not in dependent_test_reasons for item in tests):
            return tuple()
        if any(item.inclusion_reason not in dependent_build_reasons for item in build_targets):
            return tuple()
        if not tests_are_dependent and not builds_are_dependent:
            return tuple()
        evidence_paths = resolved.relevant_files[:10] or ((resolved.evidence_path,) if resolved.evidence_path is not None else tuple())
        provenance = self._evidence_assembler._merged_provenance(  # type: ignore[attr-defined]
            tuple(entry for item in tests for entry in item.provenance),
            tuple(entry for item in build_targets for entry in item.provenance),
            (
                derived_summary_provenance(
                    source_kind=SourceKind.OWNERSHIP,
                    evidence_summary="file target has no narrower direct deterministic validation surface; dependent validation surfaces are required because the file is shared",
                    evidence_paths=evidence_paths,
                ),
            ),
        )
        return (
            self._evidence_assembler.exclusion(
                item_kind=MinimumVerifiedItemKind.VALIDATION_SURFACE,
                item_id=f"validation_surface:breadth:{resolved.evidence_path or resolved.owner.id}",
                reason_code=MinimumVerifiedExclusionReason.NO_NARROWER_DIRECT_VALIDATION_SURFACE_FOR_FILE_TARGET,
                reason=(
                    "this file has no narrower direct deterministic validation surface; "
                    "the listed validations are dependent-package surfaces required because the file is shared"
                ),
                provenance=provenance,
            ),
        )

    def _structured_artifacts_for_target(
        self,
        resolved: _ResolvedMinimumTarget,
    ) -> tuple[StructuredArtifact, ...]:
        if not resolved.relevant_files:
            return tuple()
        artifacts: list[StructuredArtifact] = []
        for repository_rel_path in resolved.relevant_files:
            artifact = self._repository.describe_structured_artifact(repository_rel_path)
            if artifact is None:
                return tuple()
            artifacts.append(artifact)
        return tuple(artifacts)

    def _artifact_member_for_target(
        self,
        resolved: _ResolvedMinimumTarget,
    ) -> tuple[str, str] | None:
        if resolved.target_kind != "file" or resolved.evidence_path is None:
            return None
        if resolved.owner.kind != "component":
            return None
        component = next((item for item in self._repository.arch.get_components() if item.id == resolved.owner.id), None)
        if component is None:
            return None
        normalized = resolved.evidence_path.replace("\\", "/").strip().removeprefix("./")
        if any(normalized == root or normalized.startswith(f"{root}/") for root in component.source_roots):
            return None
        matching_roots = tuple(
            path
            for path in component.artifact_paths
            if normalized == path or normalized.startswith(f"{path}/")
        )
        if not matching_roots:
            return None
        artifact_root = max(matching_roots, key=len)
        if artifact_root != normalized and "/" in normalized:
            artifact_root = normalized.rsplit("/", 1)[0]
        return component.id, artifact_root


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
