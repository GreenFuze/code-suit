from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import (
    ImplementationFlowStepKind,
    ImplementationFlowStepRef,
    ImplementationFlowSummaryRef,
    RenderEdgeKind,
)
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_summary import preferred_source_tool
from suitcode.core.tests.models import RelatedTestTarget, ResolvedRelatedTest
from suitcode.providers.provider_roles import ProviderRole

if TYPE_CHECKING:
    from suitcode.core.code.models import CodeLocation
    from suitcode.core.models import EntityInfo
    from suitcode.core.intelligence_models import RenderEdgeRef, StaticFlowEdgeRef
    from suitcode.core.repository import Repository


class ImplementationFlowService:
    _SYMBOL_SEAM_KINDS = frozenset(
        {
            "function",
            "method",
            "class",
            "interface",
            "struct",
            "enum",
            "constructor",
        }
    )

    def __init__(self, repository: Repository) -> None:
        self._repository = repository
        self._external_reference_cache: dict[tuple[str, str], tuple["CodeLocation", ...]] = {}

    def summarize_file(
        self,
        repository_rel_path: str,
        *,
        detail_level: str,
    ) -> ImplementationFlowSummaryRef | None:
        if not self._is_eligible(repository_rel_path):
            return None
        generic_steps = self._collect_generic_steps(repository_rel_path)
        provider_steps = self._collect_provider_steps(repository_rel_path)
        merged_steps = self._dedupe_steps((*generic_steps, *provider_steps))
        if not merged_steps:
            return None
        ranked_steps = self._rank_steps(merged_steps)
        preview_steps = self._cap_steps(ranked_steps, detail_level=detail_level)
        if not preview_steps:
            return None
        provider_ids = self._provider_ids(repository_rel_path)
        provenance = self._summary_provenance(repository_rel_path, merged_steps)
        return ImplementationFlowSummaryRef(
            step_count=len(merged_steps),
            steps_preview=preview_steps,
            provider_ids=provider_ids,
            provenance=provenance,
        )

    def _is_eligible(self, repository_rel_path: str) -> bool:
        try:
            providers = self._repository.get_providers_for_file_role(repository_rel_path, ProviderRole.CODE)
        except ValueError:
            return False
        return bool(providers)

    def _collect_generic_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        symbol_steps = self._collect_symbol_anchor_steps(repository_rel_path)
        external_reference_steps = self._collect_external_reference_anchor_steps(repository_rel_path)
        test_seams = self._collect_test_seams(repository_rel_path)
        render_steps = self._render_steps(repository_rel_path)
        local_flow_steps = self._local_flow_steps(repository_rel_path)
        implementation_steps = self._implementation_anchor_steps(repository_rel_path)
        return (
            *symbol_steps,
            *external_reference_steps,
            *test_seams,
            *render_steps,
            *local_flow_steps,
            *implementation_steps,
        )

    def _collect_provider_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        return self._repository.code.get_file_implementation_flow_steps(repository_rel_path)

    def _collect_symbol_anchor_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        steps: list[ImplementationFlowStepRef] = []
        for symbol in self._ranked_symbols(repository_rel_path):
            step = self._symbol_anchor_step(symbol)
            if step is not None:
                steps.append(step)
        return tuple(steps)

    def _collect_external_reference_anchor_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        steps: list[ImplementationFlowStepRef] = []
        for symbol in self._ranked_symbols(repository_rel_path):
            step = self._external_reference_anchor_step(repository_rel_path, symbol)
            if step is not None:
                steps.append(step)
        return tuple(steps)

    def _collect_test_seams(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=repository_rel_path))
        steps: list[ImplementationFlowStepRef] = []
        for item in related_tests:
            step = self._test_seam_step(item)
            if step is None:
                continue
            steps.append(step)
            break
        return tuple(steps)

    def _ranked_symbols(self, repository_rel_path: str) -> tuple["EntityInfo", ...]:
        ranked_symbols: list[tuple[tuple[int, int, int, int], "EntityInfo"]] = []
        for symbol in self._repository.code.list_symbols_in_file(repository_rel_path):
            if not self._is_symbol_anchor_candidate(symbol):
                continue
            ranked_symbols.append((self._symbol_rank_key(repository_rel_path, symbol), symbol))
        return tuple(item for _, item in sorted(ranked_symbols, key=lambda pair: pair[0]))

    @staticmethod
    def _is_symbol_anchor_candidate(symbol: "EntityInfo") -> bool:
        if symbol.line_start is None or symbol.column_start is None:
            return False
        if not symbol.name.strip():
            return False
        return symbol.entity_kind in ImplementationFlowService._SYMBOL_SEAM_KINDS

    def _symbol_rank_key(self, repository_rel_path: str, symbol: "EntityInfo") -> tuple[int, int, int, int]:
        external_reference_count = len(self._external_references_for_symbol(repository_rel_path, symbol))
        exported = int(bool(symbol.name) and symbol.name[:1].isupper())
        return (-external_reference_count, -exported, symbol.line_start or 10**9, symbol.column_start or 10**9)

    def _symbol_anchor_step(self, symbol: "EntityInfo") -> ImplementationFlowStepRef | None:
        if symbol.line_start is None or symbol.column_start is None:
            return None
        return ImplementationFlowStepRef(
            repository_rel_path=symbol.repository_rel_path,
            line_start=symbol.line_start,
            column_start=symbol.column_start,
            step_kind=ImplementationFlowStepKind.SYMBOL_ANCHOR,
            source_label=symbol.name,
            detail_label=symbol.entity_kind,
            provenance=symbol.provenance,
        )

    def _external_reference_anchor_step(
        self,
        repository_rel_path: str,
        symbol: "EntityInfo",
    ) -> ImplementationFlowStepRef | None:
        references = self._external_references_for_symbol(repository_rel_path, symbol)
        if not references:
            return None
        anchor = references[0]
        return ImplementationFlowStepRef(
            repository_rel_path=anchor.repository_rel_path,
            line_start=anchor.line_start,
            column_start=anchor.column_start,
            step_kind=ImplementationFlowStepKind.EXTERNAL_REFERENCE_ANCHOR,
            source_label=symbol.name,
            target_label=self._path_label(anchor.repository_rel_path),
            detail_label=symbol.entity_kind,
            provenance=anchor.provenance,
        )

    def _external_references_for_symbol(
        self,
        repository_rel_path: str,
        symbol: "EntityInfo",
    ) -> tuple["CodeLocation", ...]:
        cache_key = (repository_rel_path, symbol.id)
        cached = self._external_reference_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            references = self._repository.code.find_references_by_symbol_id(symbol.id)
        except ValueError:
            self._external_reference_cache[cache_key] = tuple()
            return tuple()
        external_references = tuple(
            item
            for item in references
            if item.repository_rel_path != repository_rel_path
        )
        self._external_reference_cache[cache_key] = external_references
        return external_references

    def _render_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        render_children = self._repository.code.get_file_render_edges(
            repository_rel_path,
            relationship_kind=RenderEdgeKind.RENDERS,
        )
        render_parents = self._repository.code.get_file_render_edges(
            repository_rel_path,
            relationship_kind=RenderEdgeKind.RENDERED_BY,
        )
        return tuple(
            step
            for group in (
                tuple(self._render_step(repository_rel_path, edge) for edge in render_children),
                tuple(self._render_step(repository_rel_path, edge) for edge in render_parents),
            )
            for step in group
        )

    def _render_step(self, repository_rel_path: str, edge: RenderEdgeRef) -> ImplementationFlowStepRef:
        current_label = self._path_label(repository_rel_path)
        related_label = self._path_label(edge.repository_rel_path)
        if edge.relationship_kind == RenderEdgeKind.RENDERS:
            source_label = current_label
            target_label = related_label
        else:
            source_label = related_label
            target_label = current_label
        detail_label = self._render_detail_label(edge)
        return ImplementationFlowStepRef(
            repository_rel_path=edge.repository_rel_path,
            line_start=edge.line_start,
            column_start=edge.column_start,
            step_kind=(
                ImplementationFlowStepKind.PROP_EDGE
                if edge.prop_names
                else ImplementationFlowStepKind.RENDER_EDGE
            ),
            source_label=source_label,
            target_label=target_label,
            detail_label=detail_label,
            provenance=edge.provenance,
        )

    def _local_flow_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        edges = self._repository.code.get_file_local_flow_edges(repository_rel_path)
        return tuple(self._local_flow_step(edge) for edge in edges)

    @staticmethod
    def _local_flow_step(edge: StaticFlowEdgeRef) -> ImplementationFlowStepRef:
        return ImplementationFlowStepRef(
            repository_rel_path=edge.repository_rel_path,
            line_start=edge.line_start,
            column_start=edge.column_start,
            step_kind=ImplementationFlowStepKind.LOCAL_FLOW_EDGE,
            source_label=edge.source_label,
            target_label=edge.target_label,
            provenance=edge.provenance,
        )

    def _implementation_anchor_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        locations = self._repository.code.get_file_implementation_locations(repository_rel_path)
        return tuple(self._implementation_anchor_step(item) for item in locations)

    def _implementation_anchor_step(self, location: CodeLocation) -> ImplementationFlowStepRef:
        return ImplementationFlowStepRef(
            repository_rel_path=location.repository_rel_path,
            line_start=location.line_start,
            column_start=location.column_start,
            step_kind=ImplementationFlowStepKind.IMPLEMENTATION_ANCHOR,
            source_label=self._implementation_source_label(location),
            provenance=location.provenance,
        )

    def _test_seam_step(self, related_test: ResolvedRelatedTest) -> ImplementationFlowStepRef | None:
        if any(entry.source_kind == SourceKind.HEURISTIC for entry in related_test.provenance):
            return None
        if not related_test.test_definition.test_files:
            return None
        test_path = related_test.test_definition.test_files[0]
        return ImplementationFlowStepRef(
            repository_rel_path=test_path,
            line_start=1,
            column_start=1,
            step_kind=ImplementationFlowStepKind.TEST_SEAM,
            source_label=related_test.test_definition.name,
            detail_label=related_test.relation_reason,
            provenance=related_test.provenance,
        )

    @staticmethod
    def _dedupe_steps(steps: Sequence[ImplementationFlowStepRef]) -> tuple[ImplementationFlowStepRef, ...]:
        merged: dict[tuple[str, int, int, str, str, str | None, str | None], ImplementationFlowStepRef] = {}
        for item in steps:
            key = (
                item.repository_rel_path,
                item.line_start,
                item.column_start,
                item.step_kind.value,
                item.source_label,
                item.target_label,
                item.detail_label,
            )
            existing = merged.get(key)
            if existing is None:
                merged[key] = item
                continue
            merged[key] = item.model_copy(
                update={"provenance": tuple(dict.fromkeys((*existing.provenance, *item.provenance)))}
            )
        return tuple(merged.values())

    def _rank_steps(self, steps: Sequence[ImplementationFlowStepRef]) -> tuple[ImplementationFlowStepRef, ...]:
        return tuple(sorted(steps, key=self._step_rank_key))

    def _step_rank_key(self, item: ImplementationFlowStepRef) -> tuple[int, str, int, int, str, str, str]:
        return (
            self._step_kind_priority(item.step_kind),
            item.repository_rel_path,
            item.line_start,
            item.column_start,
            item.source_label,
            item.target_label or "",
            item.detail_label or "",
        )

    @staticmethod
    def _step_kind_priority(step_kind: ImplementationFlowStepKind) -> int:
        priorities = {
            ImplementationFlowStepKind.SYMBOL_ANCHOR: 0,
            ImplementationFlowStepKind.EXTERNAL_REFERENCE_ANCHOR: 1,
            ImplementationFlowStepKind.TEST_SEAM: 2,
            ImplementationFlowStepKind.STATE_SITE: 3,
            ImplementationFlowStepKind.EVENT_SUBSCRIBE: 4,
            ImplementationFlowStepKind.EVENT_PUBLISH: 5,
            ImplementationFlowStepKind.API_CALL: 6,
            ImplementationFlowStepKind.CONTRACT_USE: 7,
            ImplementationFlowStepKind.PROP_EDGE: 8,
            ImplementationFlowStepKind.RENDER_EDGE: 9,
            ImplementationFlowStepKind.LOCAL_FLOW_EDGE: 10,
            ImplementationFlowStepKind.IMPLEMENTATION_ANCHOR: 11,
            ImplementationFlowStepKind.RELATED_TEST_ANCHOR: 12,
        }
        return priorities[step_kind]

    def _cap_steps(
        self,
        steps: Sequence[ImplementationFlowStepRef],
        *,
        detail_level: str,
    ) -> tuple[ImplementationFlowStepRef, ...]:
        limit = self._preview_limit(detail_level)
        if len(steps) <= limit:
            return tuple(steps)
        preview = self._kind_diverse_preview(steps, limit=limit)
        if len(preview) >= limit:
            return preview
        remaining = self._remaining_preview_steps(steps, preview, limit=limit - len(preview))
        return (*preview, *remaining)

    @staticmethod
    def _preview_limit(detail_level: str) -> int:
        if detail_level == "compact":
            return 4
        if detail_level == "standard":
            return 6
        return 10

    @staticmethod
    def _kind_diverse_preview(
        steps: Sequence[ImplementationFlowStepRef],
        *,
        limit: int,
    ) -> tuple[ImplementationFlowStepRef, ...]:
        preview: list[ImplementationFlowStepRef] = []
        seen_kinds: set[ImplementationFlowStepKind] = set()
        for step in steps:
            if step.step_kind in seen_kinds:
                continue
            preview.append(step)
            seen_kinds.add(step.step_kind)
            if len(preview) >= limit:
                break
        return tuple(preview)

    @staticmethod
    def _remaining_preview_steps(
        steps: Sequence[ImplementationFlowStepRef],
        preview: Sequence[ImplementationFlowStepRef],
        *,
        limit: int,
    ) -> tuple[ImplementationFlowStepRef, ...]:
        preview_keys = {
            (
                item.repository_rel_path,
                item.line_start,
                item.column_start,
                item.step_kind,
                item.source_label,
                item.target_label,
                item.detail_label,
            )
            for item in preview
        }
        remaining: list[ImplementationFlowStepRef] = []
        for step in steps:
            key = (
                step.repository_rel_path,
                step.line_start,
                step.column_start,
                step.step_kind,
                step.source_label,
                step.target_label,
                step.detail_label,
            )
            if key in preview_keys:
                continue
            remaining.append(step)
            if len(remaining) >= limit:
                break
        return tuple(remaining)

    def _provider_ids(self, repository_rel_path: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    provider.attachment.provider_id
                    for provider in self._repository.get_providers_for_file_role(repository_rel_path, ProviderRole.CODE)
                }
            )
        )

    def _summary_provenance(
        self,
        repository_rel_path: str,
        steps: Sequence[ImplementationFlowStepRef],
    ) -> tuple[ProvenanceEntry, ...]:
        merged: list[ProvenanceEntry] = []
        for item in steps:
            for entry in item.provenance:
                if entry not in merged:
                    merged.append(entry)
        merged.append(
            derived_summary_provenance(
                source_kind=SourceKind.DEPENDENCY_GRAPH,
                source_tool=preferred_source_tool(tuple(merged)),
                evidence_summary=(
                    f"implementation-flow summary assembled from deterministic code, test, and provider-backed flow evidence for `{repository_rel_path}`"
                ),
                evidence_paths=self._summary_evidence_paths(repository_rel_path, steps),
            )
        )
        return tuple(merged)

    @staticmethod
    def _summary_evidence_paths(
        repository_rel_path: str,
        steps: Sequence[ImplementationFlowStepRef],
    ) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for step in steps:
            if step.repository_rel_path not in paths:
                paths.append(step.repository_rel_path)
            for entry in step.provenance:
                for path in entry.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _path_label(repository_rel_path: str) -> str:
        return PurePosixPath(repository_rel_path).name or repository_rel_path

    @staticmethod
    def _render_detail_label(edge: RenderEdgeRef) -> str | None:
        details: list[str] = []
        if edge.prop_names:
            details.append(", ".join(edge.prop_names[:4]))
        if edge.has_spread_props:
            details.append("spread props")
        return "; ".join(details) or None

    @staticmethod
    def _implementation_source_label(location: CodeLocation) -> str:
        if location.symbol_id:
            return location.symbol_id
        return PurePosixPath(location.repository_rel_path).name or location.repository_rel_path
