from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.intelligence_models import FileContext, SymbolContext
from suitcode.core.models import Component
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.tests.models import RelatedTestTarget, ResolvedRelatedTest

if TYPE_CHECKING:
    from suitcode.core.context_service import ContextService
    from suitcode.core.repository import Repository
    from suitcode.core.repository_models import OwnedNodeInfo


@dataclass(frozen=True)
class ResolvedImpactTarget:
    target_kind: str
    owner: OwnedNodeInfo
    evidence_path: str | None
    owner_primary_component_id: str | None
    file_primary_component_id: str | None
    file_context: FileContext | None
    symbol_context: SymbolContext | None
    reference_locations: tuple[CodeLocation, ...]
    related_tests: tuple[ResolvedRelatedTest, ...]


class ImpactTargetResolver:
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

    def resolve(
        self,
        *,
        symbol_id: str | None,
        repository_rel_path: str | None,
        owner_id: str | None,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> ResolvedImpactTarget:
        if symbol_id is not None:
            return self._resolve_symbol_target(
                symbol_id,
                reference_preview_limit=reference_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        if repository_rel_path is not None:
            return self._resolve_file_target(
                repository_rel_path,
                reference_preview_limit=reference_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        if owner_id is None:
            raise ValueError("target must include `symbol_id`, `repository_rel_path`, or `owner_id`")
        return self._resolve_owner_target(
            owner_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    def resolve_component(self, component_id: str | None) -> Component | None:
        if component_id is None:
            return None
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        try:
            return components_by_id[component_id]
        except KeyError as exc:
            raise ValueError(f"dependent component id could not be resolved: `{component_id}`") from exc

    def _resolve_symbol_target(
        self,
        symbol_id: str,
        *,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> ResolvedImpactTarget:
        symbol_context = self._context_service.describe_symbol_context(
            symbol_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        owner = symbol_context.owner
        evidence_path = symbol_context.symbol.repository_rel_path
        return ResolvedImpactTarget(
            target_kind="symbol",
            owner=owner,
            evidence_path=evidence_path,
            owner_primary_component_id=self._component_context_resolver.primary_component_id_for_owner(owner.id),
            file_primary_component_id=self._component_context_resolver.primary_component_id_for_file(evidence_path, owner.id),
            file_context=None,
            symbol_context=symbol_context,
            reference_locations=symbol_context.references_preview[:reference_preview_limit],
            related_tests=self._repository.tests.get_related_tests(
                RelatedTestTarget(repository_rel_path=evidence_path)
            )[:test_preview_limit],
        )

    def _resolve_file_target(
        self,
        repository_rel_path: str,
        *,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> ResolvedImpactTarget:
        file_owner = self._ownership_index.owner_for_file(repository_rel_path)
        owner = file_owner.owner
        file_context = None
        try:
            file_context = self._context_service.describe_files(
                (repository_rel_path,),
                symbol_preview_limit=20,
                test_preview_limit=test_preview_limit,
            )[0]
            owner = file_context.owner
        except ValueError:
            file_context = None
        try:
            reference_locations = self._code_reference_service.references_for_file(file_owner.file_info.repository_rel_path)[
                :reference_preview_limit
            ]
        except ValueError:
            reference_locations = tuple()
        if file_context is not None:
            related_tests = file_context.related_tests_preview[:test_preview_limit]
        else:
            related_tests = self._repository.tests.get_related_tests(
                RelatedTestTarget(repository_rel_path=file_owner.file_info.repository_rel_path)
            )[:test_preview_limit]
        return ResolvedImpactTarget(
            target_kind="file",
            owner=owner,
            evidence_path=file_owner.file_info.repository_rel_path,
            owner_primary_component_id=self._component_context_resolver.primary_component_id_for_owner(owner.id),
            file_primary_component_id=self._component_context_resolver.primary_component_id_for_file(
                file_owner.file_info.repository_rel_path,
                owner.id,
            ),
            file_context=file_context,
            symbol_context=None,
            reference_locations=reference_locations,
            related_tests=related_tests,
        )

    def _resolve_owner_target(
        self,
        owner_id: str,
        *,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> ResolvedImpactTarget:
        owner = self._ownership_index.owner_info(owner_id)
        try:
            references = self._code_reference_service.references_for_owner(
                owner_id,
                max_locations=reference_preview_limit,
                max_files=max(10, reference_preview_limit),
            )[:reference_preview_limit]
        except ValueError:
            references = tuple()
        return ResolvedImpactTarget(
            target_kind="owner",
            owner=owner,
            evidence_path=None,
            owner_primary_component_id=self._component_context_resolver.primary_component_id_for_owner(owner_id),
            file_primary_component_id=None,
            file_context=None,
            symbol_context=None,
            reference_locations=references,
            related_tests=self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=owner_id))[:test_preview_limit],
        )
