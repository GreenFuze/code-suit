from __future__ import annotations

from enum import StrEnum


type NodeId = str
type EvidenceId = str


class NodeKind(StrEnum):
    REPOSITORY = "repository"
    BUILD_SYSTEM = "build_system"
    COMPONENT = "component"
    AGGREGATOR = "aggregator"
    RUNNER = "runner"
    TEST_DEFINITION = "test_definition"
    PACKAGE_MANAGER = "package_manager"
    EXTERNAL_PACKAGE = "external_package"
    FILE = "file"
    ENTITY = "entity"


class EdgeKind(StrEnum):
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    FILE_CONTAINS_ENTITY = "file_contains_entity"
    RUNS = "runs"
    PRODUCES = "produces"


class BuildSystemKind(StrEnum):
    CMAKE = "cmake"
    CARGO = "cargo"
    NPM = "npm"
    PIP = "pip"
    BAZEL = "bazel"
    OTHER = "other"


class ProgrammingLanguage(StrEnum):
    PYTHON = "python"
    CPP = "cpp"
    C = "c"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    OTHER = "other"


class ComponentKind(StrEnum):
    LIBRARY = "library"
    BINARY = "binary"
    SERVICE = "service"
    PACKAGE = "package"
    OTHER = "other"


class TestFramework(StrEnum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    GTEST = "gtest"
    JUNIT = "junit"
    OTHER = "other"
