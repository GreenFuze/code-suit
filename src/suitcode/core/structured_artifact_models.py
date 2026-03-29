from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry


class StructuredArtifactKind(StrEnum):
    __test__ = False
    MARKDOWN_DOCUMENT = "markdown_document"
    OPENAPI_DOCUMENT = "openapi_document"


class MarkdownSection(StrictModel):
    heading: str
    depth: int
    line_start: int
    line_end: int
    anchor: str

    @field_validator("heading", "anchor")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text fields must not be empty")
        return value.strip()


class MarkdownCodeBlock(StrictModel):
    line_start: int
    line_end: int
    language: str | None = None


class MarkdownLink(StrictModel):
    destination: str
    line_start: int
    line_end: int
    text: str | None = None

    @field_validator("destination")
    @classmethod
    def _validate_destination(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("destination must not be empty")
        return value.strip()


class MarkdownFrontmatter(StrictModel):
    line_start: int
    line_end: int
    keys: tuple[str, ...]


class MarkdownChecklistItem(StrictModel):
    text: str
    checked: bool
    line_start: int
    line_end: int

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty")
        return value.strip()


class MarkdownDocumentStructure(StrictModel):
    section_count: int
    sections: tuple[MarkdownSection, ...]
    code_block_count: int
    code_blocks: tuple[MarkdownCodeBlock, ...]
    link_count: int
    links: tuple[MarkdownLink, ...]
    frontmatter: MarkdownFrontmatter | None = None
    checklist_item_count: int
    checklist_items: tuple[MarkdownChecklistItem, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_counts(self) -> "MarkdownDocumentStructure":
        if self.section_count != len(self.sections):
            raise ValueError("section_count must match sections length")
        if self.code_block_count != len(self.code_blocks):
            raise ValueError("code_block_count must match code_blocks length")
        if self.link_count != len(self.links):
            raise ValueError("link_count must match links length")
        if self.checklist_item_count != len(self.checklist_items):
            raise ValueError("checklist_item_count must match checklist_items length")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class OpenApiOperation(StrictModel):
    path: str
    method: str
    operation_id: str | None = None
    line_start: int | None = None
    line_end: int | None = None

    @field_validator("path", "method")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text fields must not be empty")
        return value.strip()


class OpenApiSchema(StrictModel):
    name: str
    line_start: int | None = None
    line_end: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value.strip()


class OpenApiTag(StrictModel):
    name: str
    line_start: int | None = None
    line_end: int | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value.strip()


class OpenApiDocumentStructure(StrictModel):
    spec_version: str | None = None
    path_count: int
    operations: tuple[OpenApiOperation, ...]
    schema_count: int
    schemas: tuple[OpenApiSchema, ...]
    tag_count: int
    tags: tuple[OpenApiTag, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_counts(self) -> "OpenApiDocumentStructure":
        if self.path_count != len({item.path for item in self.operations}):
            raise ValueError("path_count must match unique operation paths length")
        if self.schema_count != len(self.schemas):
            raise ValueError("schema_count must match schemas length")
        if self.tag_count != len(self.tags):
            raise ValueError("tag_count must match tags length")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class StructuredArtifact(StrictModel):
    artifact_kind: StructuredArtifactKind
    markdown: MarkdownDocumentStructure | None = None
    openapi: OpenApiDocumentStructure | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_shape(self) -> "StructuredArtifact":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        if self.artifact_kind == StructuredArtifactKind.MARKDOWN_DOCUMENT and self.markdown is None:
            raise ValueError("markdown payload is required for markdown_document artifacts")
        if self.artifact_kind == StructuredArtifactKind.OPENAPI_DOCUMENT and self.openapi is None:
            raise ValueError("openapi payload is required for openapi_document artifacts")
        return self
