from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.change_models import ChangeImpact, ChangeTarget, QualityGateInfo, RunnerImpact, TestImpact
from suitcode.core.code.models import CodeLocation
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.context_service import ContextService
from suitcode.core.intelligence_models import ComponentContext
from suitcode.core.models import Component, Runner
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, ownership_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, summarize_related_provenance
from suitcode.core.tests.models import RelatedTestTarget, ResolvedRelatedTest

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
    ) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._context_service = context_service
        self._component_context_resolver = component_context_resolver
        self._code_reference_service = code_reference_service

    def analyze_change(
        self,
        target: ChangeTarget,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        if target.symbol_id is not None:
            return self._analyze_symbol_target(
                target.symbol_id,
                reference_preview_limit=reference_preview_limit,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
                runner_preview_limit=runner_preview_limit,
            )
        if target.repository_rel_path is not None:
            return self._analyze_file_target(
                target.repository_rel_path,
                reference_preview_limit=reference_preview_limit,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
                runner_preview_limit=runner_preview_limit,
            )
        assert target.owner_id is not None
        return self._analyze_owner_target(
            target.owner_id,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
            runner_preview_limit=runner_preview_limit,
        )

    def _analyze_symbol_target(
        self,
        symbol_id: str,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        symbol_context = self._context_service.describe_symbol_context(
            symbol_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        owner = symbol_context.owner
        primary_component = self._resolve_primary_component(owner.id, symbol_context.symbol.repository_rel_path)
        component_context = self._primary_component_context(
            primary_component,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        dependent_components = self._dependent_components(primary_component, dependent_preview_limit)
        related_tests = self._related_tests_for_target(
            repository_rel_path=symbol_context.symbol.repository_rel_path,
            owner_id=None,
            test_preview_limit=test_preview_limit,
        )
        related_runners = self._related_runners_for_component(primary_component, runner_preview_limit)
        quality_gates = self._quality_gates_for_path(symbol_context.symbol.repository_rel_path)
        return ChangeImpact(
            target_kind="symbol",
            owner=owner,
            primary_component=primary_component,
            component_context=component_context,
            symbol_context=symbol_context,
            dependent_components=dependent_components,
            reference_locations=symbol_context.references_preview[:reference_preview_limit],
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
            provenance=self._change_provenance(
                owner_id=owner.id,
                dependent_components=dependent_components,
                reference_locations=symbol_context.references_preview[:reference_preview_limit],
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
                evidence_path=symbol_context.symbol.repository_rel_path,
            ),
        )

    def _analyze_file_target(
        self,
        repository_rel_path: str,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        file_context = self._context_service.describe_files(
            (repository_rel_path,),
            symbol_preview_limit=20,
            test_preview_limit=test_preview_limit,
        )[0]
        owner = file_context.owner
        primary_component = self._resolve_primary_component(owner.id, file_context.file_info.repository_rel_path)
        component_context = self._primary_component_context(
            primary_component,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        dependent_components = self._dependent_components(primary_component, dependent_preview_limit)
        references = self._code_reference_service.references_for_file(file_context.file_info.repository_rel_path)[
            :reference_preview_limit
        ]
        related_tests = self._related_tests_for_target(
            repository_rel_path=file_context.file_info.repository_rel_path,
            owner_id=None,
            test_preview_limit=test_preview_limit,
        )
        related_runners = self._related_runners_for_component(primary_component, runner_preview_limit)
        quality_gates = self._quality_gates_for_path(file_context.file_info.repository_rel_path)
        return ChangeImpact(
            target_kind="file",
            owner=owner,
            primary_component=primary_component,
            component_context=component_context,
            file_context=file_context,
            dependent_components=dependent_components,
            reference_locations=references,
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
            provenance=self._change_provenance(
                owner_id=owner.id,
                dependent_components=dependent_components,
                reference_locations=references,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
                evidence_path=file_context.file_info.repository_rel_path,
            ),
        )

    def _analyze_owner_target(
        self,
        owner_id: str,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
        runner_preview_limit: int,
    ) -> ChangeImpact:
        owner = self._ownership_index.owner_info(owner_id)
        primary_component = self._resolve_primary_component(owner_id, None)
        component_context = self._primary_component_context(
            primary_component,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        dependent_components = self._dependent_components(primary_component, dependent_preview_limit)
        references = self._code_reference_service.references_for_owner(
            owner_id,
            max_locations=reference_preview_limit,
            max_files=max(10, reference_preview_limit),
        )[:reference_preview_limit]
        related_tests = self._related_tests_for_target(
            repository_rel_path=None,
            owner_id=owner_id,
            test_preview_limit=test_preview_limit,
        )
        related_runners = self._related_runners_for_owner(owner_id, primary_component, runner_preview_limit)
        quality_gates = self._quality_gates_for_owner(owner_id)
        return ChangeImpact(
            target_kind="owner",
            owner=owner,
            primary_component=primary_component,
            component_context=component_context,
            dependent_components=dependent_components,
            reference_locations=references,
            related_tests=related_tests,
            related_runners=related_runners,
            quality_gates=quality_gates,
            provenance=self._change_provenance(
                owner_id=owner.id,
                dependent_components=dependent_components,
                reference_locations=references,
                related_tests=related_tests,
                related_runners=related_runners,
                quality_gates=quality_gates,
                evidence_path=None,
            ),
        )

    def _resolve_primary_component(self, owner_id: str, repository_rel_path: str | None) -> Component | None:
        if repository_rel_path is not None:
            component_id = self._component_context_resolver.primary_component_id_for_file(repository_rel_path, owner_id)
        else:
            component_id = self._component_context_resolver.primary_component_id_for_owner(owner_id)
        if component_id is None:
            return None
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        try:
            return components_by_id[component_id]
        except KeyError as exc:
            raise ValueError(f"dependent component id could not be resolved: `{component_id}`") from exc

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

    def _related_tests_for_target(
        self,
        repository_rel_path: str | None,
        owner_id: str | None,
        test_preview_limit: int,
    ) -> tuple[TestImpact, ...]:
        if repository_rel_path is not None:
            related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=repository_rel_path))
        else:
            assert owner_id is not None
            related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=owner_id))
        impacts: list[TestImpact] = []
        for related_test in related_tests[:test_preview_limit]:
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
