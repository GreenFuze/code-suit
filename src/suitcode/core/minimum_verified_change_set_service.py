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

        related_tests = self._candidate_resolver.related_tests(resolved)
        tests, test_exclusions = self._minimizer.minimize_tests(
            target_anchor_id=resolved.target_anchor_id,
            matches=related_tests,
        )

        build_targets, build_exclusions = self._minimizer.minimize_build_targets(
            owner=resolved.owner,
            primary_component=resolved.primary_component,
            targets=self._candidate_resolver.build_targets(),
        )

        runner_actions: tuple[MinimumVerifiedRunnerAction, ...] = tuple()
        runner_exclusions: list[ExcludedMinimumVerifiedItem] = []
        if resolved.owner.kind == "runner":
            runner_actions = self._minimizer.runner_items(
                owner=resolved.owner,
                actions=self._candidate_resolver.runner_actions(resolved.owner.id),
            )
        else:
            for runner_id in self._candidate_resolver.related_runner_ids(resolved):
                runner = self._repository.describe_runner(runner_id)
                runner_exclusions.append(
                    self._evidence_assembler.exclusion(
                        item_kind=MinimumVerifiedItemKind.RUNNER_ACTION,
                        item_id=runner.action_id,
                        reason_code=MinimumVerifiedExclusionReason.RUNNER_NOT_DIRECTLY_VALIDATION_RELEVANT,
                        reason="runner is operationally related but not required for the minimum validation set",
                        provenance=runner.provenance,
                    )
                )

        quality_validation_operations: tuple[MinimumVerifiedQualityOperation, ...] = tuple()
        quality_hygiene_operations: tuple[MinimumVerifiedQualityOperation, ...] = tuple()
        if resolved.relevant_files:
            quality_validation_operations, quality_hygiene_operations = self._quality_planner.build_operations(
                target_anchor_id=resolved.target_anchor_id,
                provider_ids=self._repository.quality.provider_ids,
                relevant_files=resolved.relevant_files,
            )

        provenance = self._overall_provenance(
            tests=tests,
            build_targets=build_targets,
            runner_actions=runner_actions,
            quality_validation_operations=quality_validation_operations,
            quality_hygiene_operations=quality_hygiene_operations,
            has_exclusions=bool(test_exclusions or build_exclusions or runner_exclusions),
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
            excluded_items=tuple((*test_exclusions, *build_exclusions, *runner_exclusions)),
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


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
