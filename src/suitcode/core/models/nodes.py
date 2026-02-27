from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from suitcode.core.models.graph_types import (
    BuildSystemKind,
    ComponentKind,
    EvidenceId,
    NodeId,
    NodeKind,
    ProgrammingLanguage,
    TestFramework,
)


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


class Aggregator(GraphNode):
    kind: Literal[NodeKind.AGGREGATOR] = NodeKind.AGGREGATOR


class Runner(GraphNode):
    kind: Literal[NodeKind.RUNNER] = NodeKind.RUNNER
    argv: tuple[str, ...] = Field(default_factory=tuple)
    cwd: str | None = None


class TestDefinition(GraphNode):
    kind: Literal[NodeKind.TEST_DEFINITION] = NodeKind.TEST_DEFINITION
    framework: TestFramework
    test_files: tuple[str, ...] = Field(default_factory=tuple)


class PackageManager(GraphNode):
    kind: Literal[NodeKind.PACKAGE_MANAGER] = NodeKind.PACKAGE_MANAGER
    manager: str
    lockfile_path: str | None = None


class ExternalPackage(GraphNode):
    kind: Literal[NodeKind.EXTERNAL_PACKAGE] = NodeKind.EXTERNAL_PACKAGE
    manager_id: str | None = None
    version_spec: str | None = None


class FileInfo(GraphNode):
    kind: Literal[NodeKind.FILE] = NodeKind.FILE
    repository_rel_path: str
    language: ProgrammingLanguage | None = None


class EntityInfo(GraphNode):
    kind: Literal[NodeKind.ENTITY] = NodeKind.ENTITY
    repository_rel_path: str
    entity_kind: str
    line_start: int | None = None
    line_end: int | None = None
    signature: str | None = None

    @field_validator("line_end")
    @classmethod
    def _validate_line_end(cls, line_end: int | None, info):
        line_start = info.data.get("line_start")
        if line_start is not None and line_end is not None and line_end < line_start:
            raise ValueError("line_end must be >= line_start")
        return line_end


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
