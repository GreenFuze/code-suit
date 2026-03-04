from __future__ import annotations

from suitcode.providers.python.quality_models import PythonQualityDiagnostic, PythonQualityOperationResult
from suitcode.providers.python.symbol_translation import PythonSymbolTranslator
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult


class PythonQualityTranslator:
    def __init__(self, symbol_translator: PythonSymbolTranslator | None = None) -> None:
        self._symbol_translator = symbol_translator or PythonSymbolTranslator()

    def to_quality_file_result(self, result: PythonQualityOperationResult) -> QualityFileResult:
        return QualityFileResult(
            repository_rel_path=result.repository_rel_path,
            tool=result.tool,
            operation=result.operation,
            changed=result.changed,
            success=result.success,
            message=result.message,
            diagnostics=tuple(self._to_diagnostic(item) for item in result.diagnostics),
            entity_delta=QualityEntityDelta(
                added=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.added),
                removed=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.removed),
                updated=tuple(self._symbol_translator.to_entity_info(item) for item in result.entity_delta.updated),
            ),
            applied_fixes=result.applied_fixes,
            content_sha_before=result.content_sha_before,
            content_sha_after=result.content_sha_after,
        )

    def _to_diagnostic(self, diagnostic: PythonQualityDiagnostic) -> QualityDiagnostic:
        return QualityDiagnostic(
            tool=diagnostic.tool,
            severity=diagnostic.severity,
            message=diagnostic.message,
            line_start=diagnostic.line_start,
            line_end=diagnostic.line_end,
            column_start=diagnostic.column_start,
            column_end=diagnostic.column_end,
            rule_id=diagnostic.rule_id,
        )
