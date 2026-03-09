from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.impact_target_resolution import ImpactTargetResolver
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
        self._target_resolver = ImpactTargetResolver(
            repository,
            ownership_index,
            context_service,
            component_context_resolver,
            code_reference_service,
        )

    def analyze_impact(
        self,
        target: ImpactTarget,
        reference_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
    ) -> ImpactSummary:
        resolved = self._target_resolver.resolve(
            symbol_id=target.symbol_id,
            repository_rel_path=target.repository_rel_path,
            owner_id=target.owner_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )
        primary_component_id = (
            resolved.owner_primary_component_id
            if resolved.target_kind in {"symbol", "owner"}
            else resolved.file_primary_component_id
        )
        dependent_ids = self._component_dependents_or_empty(primary_component_id)
        return ImpactSummary(
            target_kind=resolved.target_kind,
            owner=resolved.owner,
            primary_component_id=primary_component_id,
            dependent_component_count=len(dependent_ids),
            dependent_component_ids_preview=dependent_ids[:dependent_preview_limit],
            reference_count=len(resolved.reference_locations),
            references_preview=resolved.reference_locations[:reference_preview_limit],
            related_test_count=len(resolved.related_tests),
            related_test_ids_preview=tuple(
                item.match.test_definition.id for item in resolved.related_tests[:test_preview_limit]
            ),
            provenance=self._impact_provenance(
                owner_id=resolved.owner.id,
                symbol_path=resolved.evidence_path,
                has_references=len(resolved.reference_locations) > 0,
                dependent_ids=dependent_ids,
                related_tests=resolved.related_tests,
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
