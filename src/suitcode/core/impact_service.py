from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.intelligence_models import ImpactSummary, ImpactTarget
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.tests.models import RelatedTestTarget

if TYPE_CHECKING:
    from suitcode.core.context_service import ContextService
    from suitcode.core.repository import Repository


class ImpactService:
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

    def analyze_impact(
        self,
        target: ImpactTarget,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
    ) -> ImpactSummary:
        if target.symbol_id is not None:
            symbol_context = self._context_service.describe_symbol_context(
                target.symbol_id,
                reference_preview_limit=reference_preview_limit,
                test_preview_limit=test_preview_limit,
            )
            primary_component_id = self._component_context_resolver.primary_component_id_for_owner(symbol_context.owner.id)
            dependent_ids = self._component_dependents_or_empty(primary_component_id)
            return ImpactSummary(
                target_kind="symbol",
                owner=symbol_context.owner,
                primary_component_id=primary_component_id,
                dependent_component_count=len(dependent_ids),
                dependent_component_ids_preview=dependent_ids[:dependent_preview_limit],
                reference_count=symbol_context.reference_count,
                references_preview=symbol_context.references_preview[:reference_preview_limit],
                related_test_count=symbol_context.related_test_count,
                related_test_ids_preview=tuple(
                    item.match.test_definition.id for item in symbol_context.related_tests_preview[:test_preview_limit]
                ),
            )

        if target.repository_rel_path is not None:
            file_context = self._context_service.describe_files(
                (target.repository_rel_path,),
                symbol_preview_limit=20,
                test_preview_limit=test_preview_limit,
            )[0]
            references = self._code_reference_service.references_for_file(file_context.file_info.repository_rel_path)
            primary_component_id = self._component_context_resolver.primary_component_id_for_file(
                file_context.file_info.repository_rel_path,
                file_context.owner.id,
            )
            dependent_ids = self._component_dependents_or_empty(primary_component_id)
            return ImpactSummary(
                target_kind="file",
                owner=file_context.owner,
                primary_component_id=primary_component_id,
                dependent_component_count=len(dependent_ids),
                dependent_component_ids_preview=dependent_ids[:dependent_preview_limit],
                reference_count=len(references),
                references_preview=references[:reference_preview_limit],
                related_test_count=file_context.related_test_count,
                related_test_ids_preview=tuple(
                    item.match.test_definition.id for item in file_context.related_tests_preview[:test_preview_limit]
                ),
            )

        assert target.owner_id is not None
        owner = self._ownership_index.owner_info(target.owner_id)
        primary_component_id = self._component_context_resolver.primary_component_id_for_owner(target.owner_id)
        dependent_ids = self._component_dependents_or_empty(primary_component_id)
        references = self._code_reference_service.references_for_owner(target.owner_id)
        related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=target.owner_id))
        return ImpactSummary(
            target_kind="owner",
            owner=owner,
            primary_component_id=primary_component_id,
            dependent_component_count=len(dependent_ids),
            dependent_component_ids_preview=dependent_ids[:dependent_preview_limit],
            reference_count=len(references),
            references_preview=references[:reference_preview_limit],
            related_test_count=len(related_tests),
            related_test_ids_preview=tuple(item.match.test_definition.id for item in related_tests[:test_preview_limit]),
        )

    def _component_dependents_or_empty(self, component_id: str | None) -> tuple[str, ...]:
        if component_id is None:
            return tuple()
        return self._repository.arch.get_component_dependents(component_id)
