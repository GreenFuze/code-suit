from __future__ import annotations

from collections.abc import Callable


class ComponentIndexBuilder:
    @staticmethod
    def build(
        analyses: tuple[object, ...],
        component_id_for_analysis: Callable[[object], str],
        duplicate_message: Callable[[str], str],
    ) -> dict[str, object]:
        index: dict[str, object] = {}
        for analysis in analyses:
            component_id = component_id_for_analysis(analysis)
            if component_id in index:
                raise ValueError(duplicate_message(component_id))
            index[component_id] = analysis
        return index
