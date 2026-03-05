from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic import model_validator

from suitcode.core.models import EntityInfo
from suitcode.core.provenance import ProvenanceEntry, SourceKind


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityDiagnostic(_StrictModel):
    tool: str
    severity: str
    message: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    rule_id: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "QualityDiagnostic":
        if not self.provenance:
            raise ValueError("QualityDiagnostic.provenance must not be empty")
        source_kinds = {item.source_kind for item in self.provenance}
        if SourceKind.QUALITY_TOOL not in source_kinds:
            raise ValueError("QualityDiagnostic must include quality_tool provenance")
        invalid = source_kinds - {SourceKind.QUALITY_TOOL}
        if invalid:
            raise ValueError("QualityDiagnostic provenance may only use quality_tool in this slice")
        tool_sources = {item.source_tool for item in self.provenance if item.source_kind is SourceKind.QUALITY_TOOL}
        if tool_sources != {self.tool}:
            raise ValueError("QualityDiagnostic quality_tool provenance must match diagnostic.tool")
        return self


class QualityEntityDelta(_StrictModel):
    added: tuple[EntityInfo, ...] = Field(default_factory=tuple)
    removed: tuple[EntityInfo, ...] = Field(default_factory=tuple)
    updated: tuple[EntityInfo, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "QualityEntityDelta":
        if not self.provenance:
            raise ValueError("QualityEntityDelta.provenance must not be empty")
        if SourceKind.LSP not in {item.source_kind for item in self.provenance}:
            raise ValueError("QualityEntityDelta must include lsp provenance")
        return self


class QualityFileResult(_StrictModel):
    repository_rel_path: str
    tool: str
    operation: str
    changed: bool
    success: bool
    message: str | None = None
    diagnostics: tuple[QualityDiagnostic, ...] = Field(default_factory=tuple)
    entity_delta: QualityEntityDelta = Field(default_factory=QualityEntityDelta)
    applied_fixes: bool
    content_sha_before: str
    content_sha_after: str
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_provenance(self) -> "QualityFileResult":
        if not self.provenance:
            raise ValueError("QualityFileResult.provenance must not be empty")
        source_kinds = {item.source_kind for item in self.provenance}
        if SourceKind.QUALITY_TOOL not in source_kinds:
            raise ValueError("QualityFileResult must include quality_tool provenance")
        if SourceKind.LSP not in source_kinds:
            raise ValueError("QualityFileResult must include lsp provenance")
        quality_tool_sources = {item.source_tool for item in self.provenance if item.source_kind is SourceKind.QUALITY_TOOL}
        if quality_tool_sources != {self.tool}:
            raise ValueError("QualityFileResult quality_tool provenance must match result.tool")
        if self.entity_delta and SourceKind.LSP not in {item.source_kind for item in self.entity_delta.provenance}:
            raise ValueError("QualityFileResult entity_delta must include lsp provenance")
        if self.diagnostics:
            if any(SourceKind.QUALITY_TOOL not in {item.source_kind for item in diagnostic.provenance} for diagnostic in self.diagnostics):
                raise ValueError("QualityFileResult diagnostics must include quality_tool provenance")
        return self
