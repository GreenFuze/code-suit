from __future__ import annotations

from suitcode.providers.python.entity_delta import PythonEntityDeltaBuilder
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol


def _symbol(name: str, line_start: int, line_end: int, signature: str | None = None) -> PythonWorkspaceSymbol:
    return PythonWorkspaceSymbol(
        name=name,
        kind='function',
        repository_rel_path='src/acme/core/repository.py',
        line_start=line_start,
        line_end=line_end,
        column_start=1,
        column_end=2,
        container_name=None,
        signature=signature,
    )


def test_entity_delta_builder_detects_added_removed_and_updated() -> None:
    builder = PythonEntityDeltaBuilder()

    delta = builder.build(
        before=(_symbol('keep', 1, 2), _symbol('remove', 3, 4), _symbol('update', 5, 6, 'old')),
        after=(_symbol('keep', 1, 2), _symbol('add', 7, 8), _symbol('update', 9, 10, 'new')),
    )

    assert [item.name for item in delta.added] == ['add']
    assert [item.name for item in delta.removed] == ['remove']
    assert [item.name for item in delta.updated] == ['update']
