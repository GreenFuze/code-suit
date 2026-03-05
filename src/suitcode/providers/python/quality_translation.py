from __future__ import annotations

from suitcode.core.provenance_builders import lsp_delta_provenance, quality_tool_provenance
from suitcode.providers.python.quality_models import PythonQualityDiagnostic, PythonQualityOperationResult
from suitcode.providers.python.symbol_translation import PythonSymbolTranslator
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult


class PythonQualityTranslator:
    def __init__(self, symbol_translator: PythonSymbolTranslator | None = None) -> None:
        self._symbol_translator = symbol_translator or PythonSymbolTranslator()

    def to_quality_file_result(self, result: PythonQualityOperationResult) -> QualityFileResult:
        repository_rel_path = result.repository_rel_path
        return QualityFileResult(
            repository_rel_path=repository_rel_path,
            tool=result.tool,
            operation=result.operation,
            changed=result.changed,
            success=result.success,
            message=result.message,
            diagnostics=tuple(self._to_diagnostic(item, repository_rel_path) for item in result.diagnostics),
            entity_delta=QualityEntityDelta(
                added=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.added),
                removed=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.removed),
                updated=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.updated),
                provenance=(
                    lsp_delta_provenance(
                        source_tool="basedpyright",
                        evidence_summary=f"entity delta derived from before/after Python LSP symbols for `{repository_rel_path}`",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            ),
            applied_fixes=result.applied_fixes,
            content_sha_before=result.content_sha_before,
            content_sha_after=result.content_sha_after,
            provenance=(
                quality_tool_provenance(
                    source_tool=result.tool,
                    evidence_summary=f"{result.tool} {result.operation} result for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
                lsp_delta_provenance(
                    source_tool="basedpyright",
                    evidence_summary=f"quality result includes entity delta derived from Python LSP symbols for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )

    def _to_diagnostic(self, diagnostic: PythonQualityDiagnostic, repository_rel_path: str) -> QualityDiagnostic:
        return QualityDiagnostic(
            tool=diagnostic.tool,
            severity=diagnostic.severity,
            message=diagnostic.message,
            line_start=diagnostic.line_start,
            line_end=diagnostic.line_end,
            column_start=diagnostic.column_start,
            column_end=diagnostic.column_end,
            rule_id=diagnostic.rule_id,
            provenance=(
                quality_tool_provenance(
                    source_tool=diagnostic.tool,
                    evidence_summary=f"{diagnostic.tool} diagnostic for `{diagnostic.message}`",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )
