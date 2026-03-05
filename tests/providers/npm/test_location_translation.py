from __future__ import annotations

from suitcode.providers.npm.location_translation import NpmLocationTranslator


def test_location_translation_maps_npm_location_with_provenance() -> None:
    translator = NpmLocationTranslator()
    location = translator.to_code_location(
        ("packages/core/src/index.ts", 7, 7, 3, 9),
        operation="references",
    )

    assert location.repository_rel_path == "packages/core/src/index.ts"
    assert location.line_start == 7
    assert location.column_start == 3
    assert location.provenance[0].source_tool == "typescript-language-server"
    assert location.provenance[0].source_kind.value == "lsp"
