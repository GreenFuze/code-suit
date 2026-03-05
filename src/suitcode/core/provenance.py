from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from suitcode.core.models.ids import normalize_repository_relative_path


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfidenceMode(StrEnum):
    __test__ = False
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"
    HEURISTIC = "heuristic"


class SourceKind(StrEnum):
    __test__ = False
    MANIFEST = "manifest"
    LSP = "lsp"
    TEST_TOOL = "test_tool"
    QUALITY_TOOL = "quality_tool"
    OWNERSHIP = "ownership"
    DEPENDENCY_GRAPH = "dependency_graph"
    HEURISTIC = "heuristic"


class ProvenanceEntry(_StrictModel):
    confidence_mode: ConfidenceMode
    source_kind: SourceKind
    source_tool: str | None = None
    evidence_summary: str
    evidence_paths: tuple[str, ...] = ()

    @field_validator("source_tool")
    @classmethod
    def _validate_source_tool(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("source_tool must not be empty")
        return value

    @field_validator("evidence_summary")
    @classmethod
    def _validate_evidence_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence_summary must not be empty")
        return value.strip()

    @field_validator("evidence_paths")
    @classmethod
    def _validate_evidence_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            if not item.strip():
                raise ValueError("evidence_paths must not contain empty values")
            candidate = item.replace("\\", "/").strip()
            if "://" not in candidate and not candidate.startswith("/"):
                candidate = normalize_repository_relative_path(candidate)
            if candidate in normalized:
                raise ValueError("evidence_paths must not contain duplicates")
            normalized.append(candidate)
        return tuple(normalized)
