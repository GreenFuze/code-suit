from __future__ import annotations

from collections import Counter

from suitcode.core.change_models import (
    ChangeEvidenceEdge,
    ChangeEvidenceEdgeKind,
    ChangeEvidencePreview,
    QualityGateInfo,
    RunnerImpact,
    TestImpact,
)
from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.models import Component
from suitcode.core.repository_models import OwnedNodeInfo


class ChangeEvidenceAssembler:
    _PREVIEW_LIMIT = 25
    _ORDER = (
        ChangeEvidenceEdgeKind.TARGET_OWNER,
        ChangeEvidenceEdgeKind.OWNER_PRIMARY_COMPONENT,
        ChangeEvidenceEdgeKind.TARGET_REFERENCE,
        ChangeEvidenceEdgeKind.COMPONENT_DEPENDENT_COMPONENT,
        ChangeEvidenceEdgeKind.TARGET_RELATED_TEST,
        ChangeEvidenceEdgeKind.TARGET_RELATED_RUNNER,
        ChangeEvidenceEdgeKind.TARGET_QUALITY_GATE,
    )

    def assemble(
        self,
        *,
        target_kind: str,
        target_value: str,
        evidence_path: str | None,
        owner: OwnedNodeInfo,
        primary_component: Component | None,
        reference_locations: tuple[CodeLocation, ...],
        dependent_components: tuple[Component, ...],
        dependent_edges: tuple[ComponentDependencyEdge, ...],
        related_tests: tuple[TestImpact, ...],
        related_runners: tuple[RunnerImpact, ...],
        quality_gates: tuple[QualityGateInfo, ...],
    ) -> ChangeEvidencePreview:
        target_node_id = self._target_node_id(target_kind, target_value)
        edges = [
            self._target_owner_edge(target_kind, target_node_id, owner, evidence_path),
            *self._owner_primary_component_edges(owner, primary_component),
            *self._reference_edges(target_kind, target_node_id, reference_locations),
            *self._dependent_component_edges(primary_component, dependent_components, dependent_edges),
            *self._related_test_edges(target_kind, target_node_id, related_tests),
            *self._related_runner_edges(target_kind, target_node_id, related_runners),
            *self._quality_gate_edges(target_kind, target_node_id, quality_gates),
        ]
        ordered_edges = tuple(self._sort_edges(edges))
        counts = Counter(edge.edge_kind.value for edge in ordered_edges)
        preview = ordered_edges[: self._PREVIEW_LIMIT]
        return ChangeEvidencePreview(
            total_edges=len(ordered_edges),
            counts_by_kind=dict(sorted(counts.items())),
            edges_preview=preview,
            truncated=len(preview) < len(ordered_edges),
        )

    def _target_owner_edge(
        self,
        target_kind: str,
        target_node_id: str,
        owner: OwnedNodeInfo,
        evidence_path: str | None,
    ) -> ChangeEvidenceEdge:
        if target_kind == "file":
            reason = "owner resolved from file ownership"
        elif target_kind == "symbol":
            reason = "owner resolved from symbol file ownership"
        else:
            reason = "target directly specifies owner"
        return ChangeEvidenceEdge(
            source_node_kind="change_target",
            source_node_id=target_node_id,
            target_node_kind="owner",
            target_node_id=owner.id,
            edge_kind=ChangeEvidenceEdgeKind.TARGET_OWNER,
            reason=reason,
            provenance=self._ownership_edge_provenance(target_kind, owner.id, evidence_path),
        )

    def _owner_primary_component_edges(
        self,
        owner: OwnedNodeInfo,
        primary_component: Component | None,
    ) -> tuple[ChangeEvidenceEdge, ...]:
        if primary_component is None:
            return tuple()
        return (
            ChangeEvidenceEdge(
                source_node_kind="owner",
                source_node_id=owner.id,
                target_node_kind="component",
                target_node_id=primary_component.id,
                edge_kind=ChangeEvidenceEdgeKind.OWNER_PRIMARY_COMPONENT,
                reason="primary component resolved from ownership/component context",
                provenance=primary_component.provenance,
            ),
        )

    def _reference_edges(
        self,
        target_kind: str,
        target_node_id: str,
        reference_locations: tuple[CodeLocation, ...],
    ) -> tuple[ChangeEvidenceEdge, ...]:
        if target_kind == "symbol":
            reason = "reference discovered from symbol references"
        elif target_kind == "file":
            reason = "reference discovered from file-owned symbols"
        else:
            reason = "reference discovered from owner-backed symbols/files"
        return tuple(
            ChangeEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_node_id,
                target_node_kind="reference_location",
                target_node_id=self._reference_location_node_id(location),
                edge_kind=ChangeEvidenceEdgeKind.TARGET_REFERENCE,
                reason=reason,
                provenance=location.provenance,
            )
            for location in reference_locations
        )

    def _dependent_component_edges(
        self,
        primary_component: Component | None,
        dependent_components: tuple[Component, ...],
        dependent_edges: tuple[ComponentDependencyEdge, ...],
    ) -> tuple[ChangeEvidenceEdge, ...]:
        if primary_component is None:
            return tuple()
        edges_by_source = {
            edge.source_component_id: edge
            for edge in dependent_edges
            if edge.target_kind == "component" and edge.target_id == primary_component.id
        }
        impacts: list[ChangeEvidenceEdge] = []
        for component in dependent_components:
            try:
                dependency_edge = edges_by_source[component.id]
            except KeyError as exc:
                raise ValueError(
                    "dependent component preview item is missing matching dependency-edge provenance: "
                    f"`{component.id}` -> `{primary_component.id}`"
                ) from exc
            impacts.append(
                ChangeEvidenceEdge(
                    source_node_kind="component",
                    source_node_id=component.id,
                    target_node_kind="component",
                    target_node_id=primary_component.id,
                    edge_kind=ChangeEvidenceEdgeKind.COMPONENT_DEPENDENT_COMPONENT,
                    reason="dependent component references the primary component through architecture dependency projection",
                    provenance=dependency_edge.provenance,
                )
            )
        return tuple(impacts)

    def _related_test_edges(
        self,
        target_kind: str,
        target_node_id: str,
        related_tests: tuple[TestImpact, ...],
    ) -> tuple[ChangeEvidenceEdge, ...]:
        return tuple(
            ChangeEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_node_id,
                target_node_kind="test",
                target_node_id=item.related_test.test_definition.id,
                edge_kind=ChangeEvidenceEdgeKind.TARGET_RELATED_TEST,
                reason=item.reason,
                provenance=item.provenance,
            )
            for item in related_tests
        )

    def _related_runner_edges(
        self,
        target_kind: str,
        target_node_id: str,
        related_runners: tuple[RunnerImpact, ...],
    ) -> tuple[ChangeEvidenceEdge, ...]:
        return tuple(
            ChangeEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_node_id,
                target_node_kind="runner",
                target_node_id=item.runner.id,
                edge_kind=ChangeEvidenceEdgeKind.TARGET_RELATED_RUNNER,
                reason=item.reason,
                provenance=item.provenance,
            )
            for item in related_runners
        )

    def _quality_gate_edges(
        self,
        target_kind: str,
        target_node_id: str,
        quality_gates: tuple[QualityGateInfo, ...],
    ) -> tuple[ChangeEvidenceEdge, ...]:
        return tuple(
            ChangeEvidenceEdge(
                source_node_kind="change_target",
                source_node_id=target_node_id,
                target_node_kind="quality_gate",
                target_node_id=self._quality_gate_node_id(item.provider_id),
                edge_kind=ChangeEvidenceEdgeKind.TARGET_QUALITY_GATE,
                reason=item.reason,
                provenance=item.provenance,
            )
            for item in quality_gates
        )

    def _sort_edges(self, edges: list[ChangeEvidenceEdge]) -> list[ChangeEvidenceEdge]:
        order_index = {kind.value: index for index, kind in enumerate(self._ORDER)}
        return sorted(
            edges,
            key=lambda item: (
                order_index[item.edge_kind.value],
                item.source_node_id,
                item.target_node_id,
                item.reason,
            ),
        )

    @staticmethod
    def _target_node_id(target_kind: str, target_value: str) -> str:
        return f"change_target:{target_kind}:{target_value}"

    @staticmethod
    def _reference_location_node_id(location: CodeLocation) -> str:
        return f"location:{location.repository_rel_path}:{location.line_start}:{location.column_start}"

    @staticmethod
    def _quality_gate_node_id(provider_id: str) -> str:
        return f"quality_gate:{provider_id}"

    @staticmethod
    def _ownership_edge_provenance(
        target_kind: str,
        owner_id: str,
        evidence_path: str | None,
    ):
        from suitcode.core.provenance_builders import ownership_provenance

        if target_kind == "owner":
            summary = f"owner `{owner_id}` was provided directly as the change target"
            paths = ()
        else:
            summary = f"owner `{owner_id}` resolved from ownership metadata"
            paths = ((evidence_path,) if evidence_path is not None else ())
        return (
            ownership_provenance(
                evidence_summary=summary,
                evidence_paths=paths,
            ),
        )
