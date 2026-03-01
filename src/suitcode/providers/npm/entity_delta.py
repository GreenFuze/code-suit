from __future__ import annotations

from collections import defaultdict

from suitcode.providers.npm.quality_models import NpmQualityEntityDelta
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol


class NpmEntityDeltaBuilder:
    def build(
        self,
        before: tuple[NpmWorkspaceSymbol, ...],
        after: tuple[NpmWorkspaceSymbol, ...],
    ) -> NpmQualityEntityDelta:
        before_by_anchor = self._group_by_anchor(before)
        after_by_anchor = self._group_by_anchor(after)
        added: list[NpmWorkspaceSymbol] = []
        removed: list[NpmWorkspaceSymbol] = []
        updated: list[NpmWorkspaceSymbol] = []

        for anchor in sorted(set(before_by_anchor) | set(after_by_anchor)):
            before_items = sorted(before_by_anchor.get(anchor, []), key=self._sort_key)
            after_items = sorted(after_by_anchor.get(anchor, []), key=self._sort_key)
            shared_count = min(len(before_items), len(after_items))
            for index in range(shared_count):
                if self._state(before_items[index]) != self._state(after_items[index]):
                    updated.append(after_items[index])
            if len(before_items) > shared_count:
                removed.extend(before_items[shared_count:])
            if len(after_items) > shared_count:
                added.extend(after_items[shared_count:])

        return NpmQualityEntityDelta(
            added=tuple(sorted(added, key=self._sort_key)),
            removed=tuple(sorted(removed, key=self._sort_key)),
            updated=tuple(sorted(updated, key=self._sort_key)),
        )

    def _group_by_anchor(
        self,
        items: tuple[NpmWorkspaceSymbol, ...],
    ) -> dict[tuple[str, str, str], list[NpmWorkspaceSymbol]]:
        grouped: dict[tuple[str, str, str], list[NpmWorkspaceSymbol]] = defaultdict(list)
        for item in items:
            grouped[(item.repository_rel_path, item.kind, item.name)].append(item)
        return grouped

    def _state(self, item: NpmWorkspaceSymbol) -> tuple[object, ...]:
        return (
            item.line_start,
            item.line_end,
            item.column_start,
            item.column_end,
            item.signature,
        )

    def _sort_key(self, item: NpmWorkspaceSymbol) -> tuple[object, ...]:
        return (
            item.name,
            item.kind,
            item.line_start or 0,
            item.column_start or 0,
            item.repository_rel_path,
        )
