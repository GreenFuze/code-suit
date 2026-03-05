from __future__ import annotations

from suitcode.providers.python.location_translation import PythonLocationTranslator


def test_location_translation_maps_python_location_with_provenance() -> None:
    translator = PythonLocationTranslator()
    location = translator.to_code_location(
        ("src/acme/core/repository.py", 5, 5, 3, 8),
        operation="definition",
    )

    assert location.repository_rel_path == "src/acme/core/repository.py"
    assert location.line_start == 5
    assert location.column_start == 3
    assert location.provenance[0].source_tool == "basedpyright"
    assert location.provenance[0].source_kind.value == "lsp"
