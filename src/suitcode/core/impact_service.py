from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.intelligence_models import ImpactSummary, ImpactTarget
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, ownership_provenance
from suitcode.core.tests.provenance import is_authoritative_test_provenance
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
                provenance=self._impact_provenance(
                    owner_id=symbol_context.owner.id,
                    symbol_path=symbol_context.symbol.repository_rel_path,
                    has_references=symbol_context.reference_count > 0,
                    dependent_ids=dependent_ids,
                    related_tests=symbol_context.related_tests_preview,
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
                provenance=self._impact_provenance(
                    owner_id=file_context.owner.id,
                    symbol_path=file_context.file_info.repository_rel_path,
                    has_references=len(references) > 0,
                    dependent_ids=dependent_ids,
                    related_tests=file_context.related_tests_preview,
                ),
            )

        if target.owner_id is None:
            raise ValueError("impact target must include `symbol_id`, `repository_rel_path`, or `owner_id`")
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
            provenance=self._impact_provenance(
                owner_id=target.owner_id,
                symbol_path=None,
                has_references=len(references) > 0,
                dependent_ids=dependent_ids,
                related_tests=related_tests,
            ),
        )

    def _component_dependents_or_empty(self, component_id: str | None) -> tuple[str, ...]:
        if component_id is None:
            return tuple()
        return self._repository.arch.get_component_dependents(component_id)

    def _impact_provenance(
        self,
        owner_id: str,
        symbol_path: str | None,
        has_references: bool,
        dependent_ids: tuple[str, ...],
        related_tests,
    ) -> tuple[ProvenanceEntry, ...]:
        entries: list[ProvenanceEntry] = [
            ownership_provenance(
                evidence_summary=f"impact analysis anchored to owner `{owner_id}` via ownership index",
                evidence_paths=((symbol_path,) if symbol_path is not None else ()),
            )
        ]
        if dependent_ids:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.MANIFEST,
                    evidence_summary=f"dependent component impact derived from {len(dependent_ids)} dependency edges",
                    evidence_paths=(),
                )
            )
        if has_references and symbol_path is not None:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.LSP,
                    evidence_summary="reference impact derived from LSP definition/reference results",
                    evidence_paths=(symbol_path,),
                    source_tool="basedpyright" if symbol_path.lower().endswith(".py") else "typescript-language-server",
                )
            )
        if related_tests:
            paths: list[str] = []
            authoritative = True
            for related_test in related_tests:
                authoritative = authoritative and is_authoritative_test_provenance(related_test.provenance)
                for provenance in related_test.provenance:
                    for path in provenance.evidence_paths:
                        if path not in paths:
                            paths.append(path)
            entries.append(
                ProvenanceEntry(
                    confidence_mode=("authoritative" if authoritative else "derived"),
                    source_kind=(SourceKind.TEST_TOOL if authoritative else SourceKind.HEURISTIC),
                    source_tool=None,
                    evidence_summary="related test impact derived from discovered test metadata",
                    evidence_paths=tuple(paths[:10]),
                )
            )
        return tuple(entries)
