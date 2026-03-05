from __future__ import annotations

from suitcode.providers.python.quality_models import (
    PythonQualityDiagnostic,
    PythonQualityEntityDelta,
    PythonQualityOperationResult,
)
from suitcode.providers.python.quality_translation import PythonQualityTranslator
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol


def _symbol(name: str) -> PythonWorkspaceSymbol:
    return PythonWorkspaceSymbol(
        name=name,
        kind="function",
        repository_rel_path="src/acme/core/repository.py",
        line_start=1,
        line_end=2,
        column_start=1,
        column_end=10,
        container_name=None,
        signature=None,
    )


def test_quality_translation_maps_internal_python_result_to_public_result() -> None:
    translator = PythonQualityTranslator()

    result = translator.to_quality_file_result(
        PythonQualityOperationResult(
            repository_rel_path="src/acme/core/repository.py",
            tool="ruff",
            operation="lint",
            changed=True,
            success=True,
            message="ok",
            diagnostics=(PythonQualityDiagnostic(tool="ruff", severity="warning", message="issue", line_start=1),),
            entity_delta=PythonQualityEntityDelta(added=(_symbol("new_fn"),), updated=(_symbol("updated_fn"),)),
            applied_fixes=True,
            content_sha_before="before",
            content_sha_after="after",
        )
    )

    assert result.tool == "ruff"
    assert result.changed is True
    assert result.diagnostics[0].provenance[0].source_kind.value == "quality_tool"
    assert [item.name for item in result.entity_delta.added] == ["new_fn"]
    assert [item.name for item in result.entity_delta.updated] == ["updated_fn"]
    assert result.entity_delta.provenance[0].source_kind.value == "lsp"
    assert {item.source_kind.value for item in result.provenance} == {"quality_tool", "lsp"}
