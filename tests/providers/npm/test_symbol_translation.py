from __future__ import annotations

from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from suitcode.providers.npm.symbol_translation import NpmSymbolTranslator


def test_symbol_translation_maps_npm_symbol_to_entity_info() -> None:
    translator = NpmSymbolTranslator()

    entity = translator.to_entity_info(
        NpmWorkspaceSymbol(
            name="Core",
            kind="class",
            repository_rel_path="packages/core/src/index.ts",
            line_start=1,
            line_end=11,
            column_start=1,
            column_end=2,
            container_name=None,
            signature="CoreContainer",
        )
    )

    assert entity.id == "entity:packages/core/src/index.ts:class:Core:1-11"
    assert entity.repository_rel_path == "packages/core/src/index.ts"
    assert entity.entity_kind == "class"
    assert entity.column_start == 1
    assert entity.signature == "CoreContainer"
