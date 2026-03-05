from __future__ import annotations

from suitcode.providers.npm.quality_models import (
    NpmQualityDiagnostic,
    NpmQualityEntityDelta,
    NpmQualityOperationResult,
)
from suitcode.providers.npm.quality_translation import NpmQualityTranslator
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol


def _symbol(name: str) -> NpmWorkspaceSymbol:
    return NpmWorkspaceSymbol(
        name=name,
        kind="function",
        repository_rel_path="packages/core/src/index.ts",
        line_start=1,
        line_end=2,
        column_start=1,
        column_end=10,
        container_name=None,
        signature=None,
    )


def test_quality_translation_maps_internal_result_to_public_result() -> None:
    translator = NpmQualityTranslator()

    result = translator.to_quality_file_result(
        NpmQualityOperationResult(
            repository_rel_path="packages/core/src/index.ts",
            tool="eslint",
            operation="lint",
            changed=True,
            success=True,
            message="ok",
            diagnostics=(NpmQualityDiagnostic(tool="eslint", severity="warning", message="issue", line_start=1),),
            entity_delta=NpmQualityEntityDelta(added=(_symbol("newFn"),), updated=(_symbol("updatedFn"),)),
            applied_fixes=True,
            content_sha_before="before",
            content_sha_after="after",
        )
    )

    assert result.tool == "eslint"
    assert result.changed is True
    assert result.diagnostics[0].message == "issue"
    assert result.diagnostics[0].provenance[0].source_kind.value == "quality_tool"
    assert [item.name for item in result.entity_delta.added] == ["newFn"]
    assert [item.name for item in result.entity_delta.updated] == ["updatedFn"]
    assert result.entity_delta.provenance[0].source_kind.value == "lsp"
    assert {item.source_kind.value for item in result.provenance} == {"quality_tool", "lsp"}
