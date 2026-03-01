from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from suitcode.core.models import EntityInfo


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


class QualityEntityDelta(_StrictModel):
    added: tuple[EntityInfo, ...] = Field(default_factory=tuple)
    removed: tuple[EntityInfo, ...] = Field(default_factory=tuple)
    updated: tuple[EntityInfo, ...] = Field(default_factory=tuple)


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
