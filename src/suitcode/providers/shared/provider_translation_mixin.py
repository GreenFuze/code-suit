from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from typing import TypeVar

from suitcode.core.intelligence_models import ComponentDependencyEdge

TSource = TypeVar("TSource")
TTarget = TypeVar("TTarget")


class ProviderTranslationMixin:
    @staticmethod
    def _translate_sorted(
        items: Iterable[TSource],
        translator: Callable[[TSource], TTarget],
        *,
        key: Callable[[TTarget], object],
    ) -> tuple[TTarget, ...]:
        translated = (translator(item) for item in items)
        return tuple(sorted(translated, key=key))

    @staticmethod
    def _filter_dependency_edges(
        component_id: str | None,
        edges: tuple[ComponentDependencyEdge, ...],
        known_component_ids: Collection[str],
    ) -> tuple[ComponentDependencyEdge, ...]:
        if component_id is None:
            return edges
        if component_id not in known_component_ids:
            raise ValueError(f"unknown component id: `{component_id}`")
        return tuple(item for item in edges if item.source_component_id == component_id)
