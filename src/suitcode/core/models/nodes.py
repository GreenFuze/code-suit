from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from suitcode.core.models.graph_types import (
    BuildSystemKind,
    ComponentKind,
    EvidenceId,
    NodeId,
    NodeKind,
    ProgrammingLanguage,
    TestFramework,
)
from suitcode.core.provenance import ProvenanceEntry, SourceKind


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    id: EvidenceId
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    tool: str | None = None
    message: str | None = None
    log_path: str | None = None

    @field_validator("line_end")
    @classmethod
    def _validate_line_end(cls, line_end: int | None, info):
        line_start = info.data.get("line_start")
        if line_start is not None and line_end is not None and line_end < line_start:
            raise ValueError("line_end must be >= line_start")
        return line_end


class GraphNode(StrictModel):
    id: NodeId
    kind: NodeKind
    name: str
    evidence_ids: tuple[EvidenceId, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceEntry, ...] = Field(default_factory=tuple)


class RepositoryInfo(GraphNode):
    kind: Literal[NodeKind.REPOSITORY] = NodeKind.REPOSITORY
    root_path: str


class BuildSystemInfo(GraphNode):
    kind: Literal[NodeKind.BUILD_SYSTEM] = NodeKind.BUILD_SYSTEM
    build_system: BuildSystemKind
    configuration_name: str
    tool_version: str | None = None
    structural_fingerprint: str | None = None


class Component(GraphNode):
    kind: Literal[NodeKind.COMPONENT] = NodeKind.COMPONENT
    component_kind: ComponentKind
    language: ProgrammingLanguage
    source_roots: tuple[str, ...] = Field(default_factory=tuple)
    artifact_paths: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("component provenance must not be empty")
        for item in self.provenance:
            if item.source_kind == SourceKind.LSP:
                raise ValueError("component provenance must not be sourced from lsp")
        return self


class Aggregator(GraphNode):
    kind: Literal[NodeKind.AGGREGATOR] = NodeKind.AGGREGATOR

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("aggregator provenance must not be empty")
        for item in self.provenance:
            if item.source_kind == SourceKind.LSP:
                raise ValueError("aggregator provenance must not be sourced from lsp")
        return self


class Runner(GraphNode):
    kind: Literal[NodeKind.RUNNER] = NodeKind.RUNNER
    argv: tuple[str, ...] = Field(default_factory=tuple)
    cwd: str | None = None

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("runner provenance must not be empty")
        if all(item.source_kind == SourceKind.OWNERSHIP for item in self.provenance):
            raise ValueError("runner provenance must not be ownership-only")
        return self


class TestDefinition(GraphNode):
    kind: Literal[NodeKind.TEST_DEFINITION] = NodeKind.TEST_DEFINITION
    framework: TestFramework
    test_files: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("test definition provenance must not be empty")
        return self


class PackageManager(GraphNode):
    kind: Literal[NodeKind.PACKAGE_MANAGER] = NodeKind.PACKAGE_MANAGER
    manager: str
    lockfile_path: str | None = None

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("package manager provenance must not be empty")
        for item in self.provenance:
            if item.source_kind == SourceKind.LSP:
                raise ValueError("package manager provenance must not be sourced from lsp")
        return self


class ExternalPackage(GraphNode):
    kind: Literal[NodeKind.EXTERNAL_PACKAGE] = NodeKind.EXTERNAL_PACKAGE
    manager_id: str | None = None
    version_spec: str | None = None

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("external package provenance must not be empty")
        for item in self.provenance:
            if item.source_kind == SourceKind.LSP:
                raise ValueError("external package provenance must not be sourced from lsp")
        return self


class FileInfo(GraphNode):
    kind: Literal[NodeKind.FILE] = NodeKind.FILE
    repository_rel_path: str
    language: ProgrammingLanguage | None = None
    owner_id: NodeId

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("file provenance must not be empty")
        return self


class EntityInfo(GraphNode):
    kind: Literal[NodeKind.ENTITY] = NodeKind.ENTITY
    repository_rel_path: str
    entity_kind: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    signature: str | None = None

    @model_validator(mode="after")
    def _validate_provenance(self):
        if not self.provenance:
            raise ValueError("entity provenance must not be empty")
        if all(item.source_kind != SourceKind.LSP for item in self.provenance):
            raise ValueError("entity provenance must include lsp evidence")
        return self

    @field_validator("line_end")
    @classmethod
    def _validate_line_end(cls, line_end: int | None, info):
        line_start = info.data.get("line_start")
        if line_start is not None and line_end is not None and line_end < line_start:
            raise ValueError("line_end must be >= line_start")
        return line_end

    @field_validator("column_end")
    @classmethod
    def _validate_column_end(cls, column_end: int | None, info):
        column_start = info.data.get("column_start")
        if column_start is not None and column_end is not None and column_end < column_start:
            raise ValueError("column_end must be >= column_start")
        return column_end


NODE_MODEL_BY_KIND: dict[NodeKind, type[GraphNode]] = {
    NodeKind.REPOSITORY: RepositoryInfo,
    NodeKind.BUILD_SYSTEM: BuildSystemInfo,
    NodeKind.COMPONENT: Component,
    NodeKind.AGGREGATOR: Aggregator,
    NodeKind.RUNNER: Runner,
    NodeKind.TEST_DEFINITION: TestDefinition,
    NodeKind.PACKAGE_MANAGER: PackageManager,
    NodeKind.EXTERNAL_PACKAGE: ExternalPackage,
    NodeKind.FILE: FileInfo,
    NodeKind.ENTITY: EntityInfo,
}


def parse_node(payload: dict) -> GraphNode:
    kind = NodeKind(payload["kind"])
    model = NODE_MODEL_BY_KIND[kind]
    return model.model_validate(payload)
