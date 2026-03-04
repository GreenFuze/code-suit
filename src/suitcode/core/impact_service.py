from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ImpactSummary, ImpactTarget
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.tests.models import RelatedTestTarget

if TYPE_CHECKING:
    from suitcode.core.context_service import ContextService
    from suitcode.core.repository import Repository


class ImpactService:
    def __init__(self, repository: Repository, ownership_index: OwnershipIndex, context_service: ContextService) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._context_service = context_service

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
            primary_component_id = self.primary_component_id_for_owner(symbol_context.owner.id)
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
                    match.test_definition.id for match in symbol_context.related_tests_preview[:test_preview_limit]
                ),
            )

        if target.repository_rel_path is not None:
            file_context = self._context_service.describe_files(
                (target.repository_rel_path,),
                symbol_preview_limit=20,
                test_preview_limit=test_preview_limit,
            )[0]
            references = self.references_for_file(file_context.file_info.repository_rel_path)
            primary_component_id = self.primary_component_id_for_file(
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
                    match.test_definition.id for match in file_context.related_tests_preview[:test_preview_limit]
                ),
            )

        assert target.owner_id is not None
        owner = self._ownership_index.owner_info(target.owner_id)
        primary_component_id = self.primary_component_id_for_owner(target.owner_id)
        dependent_ids = self._component_dependents_or_empty(primary_component_id)
        references = self.references_for_owner(target.owner_id)
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
            related_test_ids_preview=tuple(match.test_definition.id for match in related_tests[:test_preview_limit]),
        )

    def primary_component_id_for_owner(self, owner_id: str) -> str | None:
        owner = self._ownership_index.owner_info(owner_id)
        if owner.kind == "component":
            return owner.id
        component_ids = {
            self.primary_component_id_for_file(file_info.repository_rel_path, owner.id)
            for file_info in self._ownership_index.files_for_owner(owner_id)
        }
        component_ids.discard(None)
        if not component_ids:
            return None
        if len(component_ids) > 1:
            raise ValueError(f"owner resolves to multiple component contexts: `{owner_id}`")
        return next(iter(component_ids))

    def primary_component_id_for_file(self, repository_rel_path: str, owner_id: str) -> str | None:
        owner = self._ownership_index.owner_info(owner_id)
        if owner.kind == "component":
            return owner.id
        candidates: list[str] = []
        for component in self._repository.arch.get_components():
            component_files = self._ownership_index.files_for_owner(component.id)
            if any(item.repository_rel_path == repository_rel_path for item in component_files):
                candidates.append(component.id)
                continue
            if any(repository_rel_path == root or repository_rel_path.startswith(f"{root}/") for root in component.source_roots):
                candidates.append(component.id)
        candidates = sorted(set(candidates))
        if not candidates:
            return None
        if len(candidates) > 1:
            raise ValueError(f"file resolves to multiple component contexts: `{repository_rel_path}`")
        return candidates[0]

    def references_for_file(self, repository_rel_path: str) -> tuple[CodeLocation, ...]:
        references: dict[tuple[str, int, int, int | None, int | None, str | None], CodeLocation] = {}
        for symbol in self._repository.code.list_symbols_in_file(repository_rel_path):
            for location in self._repository.code.find_references_by_symbol_id(symbol.id):
                key = (
                    location.repository_rel_path,
                    location.line_start,
                    location.column_start,
                    location.line_end,
                    location.column_end,
                    location.symbol_id,
                )
                references.setdefault(key, location)
        return tuple(
            sorted(
                references.values(),
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def references_for_owner(self, owner_id: str) -> tuple[CodeLocation, ...]:
        references: dict[tuple[str, int, int, int | None, int | None, str | None], CodeLocation] = {}
        for file_info in self._ownership_index.files_for_owner(owner_id):
            for location in self.references_for_file(file_info.repository_rel_path):
                key = (
                    location.repository_rel_path,
                    location.line_start,
                    location.column_start,
                    location.line_end,
                    location.column_end,
                    location.symbol_id,
                )
                references.setdefault(key, location)
        return tuple(
            sorted(
                references.values(),
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def _component_dependents_or_empty(self, component_id: str | None) -> tuple[str, ...]:
        if component_id is None:
            return tuple()
        return self._repository.arch.get_component_dependents(component_id)
