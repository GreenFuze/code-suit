from __future__ import annotations

from suitcode.core.intelligence_models import ComponentDependencyEdge, DependencyRef


class DependencyProjection:
    @staticmethod
    def refs_for_component(edges: tuple[ComponentDependencyEdge, ...], component_id: str) -> tuple[DependencyRef, ...]:
        refs = [
            DependencyRef(
                target_id=edge.target_id,
                target_kind=edge.target_kind,
                dependency_scope=edge.dependency_scope,
                provenance=edge.provenance,
            )
            for edge in edges
            if edge.source_component_id == component_id
        ]
        return tuple(
            sorted(
                refs,
                key=lambda item: (item.target_kind, item.target_id, item.dependency_scope),
            )
        )

    @staticmethod
    def dependents_for_component(edges: tuple[ComponentDependencyEdge, ...], component_id: str) -> tuple[str, ...]:
        dependents = {
            edge.source_component_id
            for edge in edges
            if edge.target_kind == "component" and edge.target_id == component_id
        }
        return tuple(sorted(dependents))

