from __future__ import annotations

from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol
from suitcode.providers.python.symbol_translation import PythonSymbolTranslator


def test_symbol_translation_maps_python_symbol_to_entity_info() -> None:
    translator = PythonSymbolTranslator()

    entity = translator.to_entity_info(
        PythonWorkspaceSymbol(
            name="RepositoryManager",
            kind="class",
            repository_rel_path="src/acme/core/repository.py",
            line_start=1,
            line_end=7,
            column_start=1,
            column_end=2,
            container_name=None,
            signature="RepositoryManager",
        )
    )

    assert entity.id == "entity:src/acme/core/repository.py:class:RepositoryManager:1-7"
    assert entity.repository_rel_path == "src/acme/core/repository.py"
    assert entity.entity_kind == "class"
    assert entity.column_start == 1
    assert entity.signature == "RepositoryManager"
    assert entity.provenance[0].source_tool == "basedpyright"
