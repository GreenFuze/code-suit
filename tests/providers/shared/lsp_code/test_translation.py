from __future__ import annotations

from suitcode.providers.shared.lsp_code.backend import LspRepositorySymbol
from suitcode.providers.shared.lsp_code.translation import LspEntityTranslatorBase, LspLocationTranslatorBase


def test_entity_translation_base_maps_entity_and_provenance() -> None:
    translator = LspEntityTranslatorBase(
        source_tool="basedpyright",
        evidence_summary="discovered from Python LSP symbol information",
    )
    entity = translator.to_entity_info(
        LspRepositorySymbol(
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
    assert entity.provenance[0].source_tool == "basedpyright"
    assert entity.provenance[0].evidence_summary == "discovered from Python LSP symbol information"


def test_location_translation_base_maps_location_and_provenance() -> None:
    translator = LspLocationTranslatorBase(source_tool="typescript-language-server")
    location = translator.to_code_location(
        ("packages/core/src/index.ts", 5, 6, 1, 3),
        operation="definition",
    )

    assert location.repository_rel_path == "packages/core/src/index.ts"
    assert location.line_start == 5
    assert location.column_start == 1
    assert location.provenance[0].source_tool == "typescript-language-server"
