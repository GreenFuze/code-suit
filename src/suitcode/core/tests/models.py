from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel, TestDefinition
from suitcode.core.provenance import ConfidenceMode, ProvenanceEntry, SourceKind
from suitcode.core.tests.provenance import (
    is_authoritative_test_provenance,
    summarize_test_provenance_kind,
    summarize_test_provenance_tool,
)


class RelatedTestTarget(StrictModel):
    repository_rel_path: str | None = None
    owner_id: str | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "RelatedTestTarget":
        has_path = self.repository_rel_path is not None
        has_owner = self.owner_id is not None
        if has_path == has_owner:
            raise ValueError("exactly one of repository_rel_path or owner_id must be provided")
        if has_path:
            self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        elif self.owner_id is not None and not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        return self


class TestDiscoveryMethod(StrEnum):
    __test__ = False
    AUTHORITATIVE_PYTEST_COLLECT = "authoritative_pytest_collect"
    AUTHORITATIVE_JEST_LIST_TESTS = "authoritative_jest_list_tests"
    HEURISTIC_MANIFEST_GLOB = "heuristic_manifest_glob"
    HEURISTIC_CONFIG_GLOB = "heuristic_config_glob"
    HEURISTIC_UNITTEST = "heuristic_unittest"


class RelatedTestMatch(StrictModel):
    test_definition: TestDefinition
    relation_reason: str
    matched_owner_id: str | None = None
    matched_repository_rel_path: str | None = None

    @model_validator(mode="after")
    def _validate_reason_and_match(self) -> "RelatedTestMatch":
        allowed = {"same_owner", "same_component", "same_package", "repository_default_suite"}
        if self.relation_reason not in allowed:
            raise ValueError(f"unsupported relation_reason: `{self.relation_reason}`")
        if self.matched_repository_rel_path is not None:
            self.matched_repository_rel_path = normalize_repository_relative_path(self.matched_repository_rel_path)
        return self


class DiscoveredTestDefinition(StrictModel):
    test_definition: TestDefinition
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_test_provenance(self) -> "DiscoveredTestDefinition":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        source_kinds = {item.source_kind for item in self.provenance}
        if not source_kinds.intersection({SourceKind.TEST_TOOL, SourceKind.HEURISTIC}):
            raise ValueError("discovered tests must include test-tool or heuristic provenance")
        if (
            is_authoritative_test_provenance(self.provenance)
            and ConfidenceMode.AUTHORITATIVE not in {item.confidence_mode for item in self.provenance}
        ):
            raise ValueError("authoritative discovered tests must include authoritative provenance")
        return self

    @property
    def is_authoritative(self) -> bool:
        return is_authoritative_test_provenance(self.provenance)

    @property
    def primary_source_tool(self) -> str | None:
        return summarize_test_provenance_tool(self.provenance)

    @property
    def primary_source_kind(self) -> SourceKind:
        return summarize_test_provenance_kind(self.provenance)


class ResolvedRelatedTest(StrictModel):
    match: RelatedTestMatch
    discovered_test: DiscoveredTestDefinition

    @model_validator(mode="after")
    def _validate_join(self) -> "ResolvedRelatedTest":
        if self.match.test_definition.id != self.discovered_test.test_definition.id:
            raise ValueError("match and discovered_test must reference the same test_definition id")
        return self

    @property
    def test_definition(self) -> TestDefinition:
        return self.match.test_definition

    @property
    def relation_reason(self) -> str:
        return self.match.relation_reason

    @property
    def matched_owner_id(self) -> str | None:
        return self.match.matched_owner_id

    @property
    def matched_repository_rel_path(self) -> str | None:
        return self.match.matched_repository_rel_path

    @property
    def provenance(self) -> tuple[ProvenanceEntry, ...]:
        return self.discovered_test.provenance

    @property
    def is_authoritative(self) -> bool:
        return self.discovered_test.is_authoritative


class TestExecutionStatus(StrEnum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class TestTargetDescription(StrictModel):
    test_definition: TestDefinition
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    is_authoritative: bool
    warning: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("command_argv")
    @classmethod
    def _validate_command_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("command_argv must not be empty")
        if any(not item.strip() for item in value):
            raise ValueError("command_argv must not contain empty arguments")
        return value

    @field_validator("command_cwd")
    @classmethod
    def _validate_command_cwd(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("command_cwd must not be empty")
        return value

    @field_validator("warning")
    @classmethod
    def _validate_warning(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("warning must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_description(self) -> "TestTargetDescription":
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        source_kinds = {item.source_kind for item in self.provenance}
        if not source_kinds.intersection({SourceKind.TEST_TOOL, SourceKind.HEURISTIC}):
            raise ValueError("test target description must include test-tool or heuristic provenance")
        if self.is_authoritative and ConfidenceMode.AUTHORITATIVE not in {item.confidence_mode for item in self.provenance}:
            raise ValueError("authoritative test target descriptions must include authoritative provenance")
        if not self.is_authoritative and self.warning is None:
            raise ValueError("heuristic test target descriptions must include warning")
        return self


class TestFailureSnippet(StrictModel):
    repository_rel_path: str
    line_start: int
    line_end: int
    snippet: str
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_snippet(self) -> "TestFailureSnippet":
        self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        if self.line_start < 1:
            raise ValueError("line_start must be >= 1")
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        if not self.snippet.strip():
            raise ValueError("snippet must not be empty")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class TestExecutionResult(StrictModel):
    test_id: str
    status: TestExecutionStatus
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    warning: str | None = None
    output_excerpt: str | None = None
    failure_snippets: tuple[TestFailureSnippet, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("test_id")
    @classmethod
    def _validate_test_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("test_id must not be empty")
        return value

    @field_validator("command_argv")
    @classmethod
    def _validate_command_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("command_argv must not be empty")
        if any(not item.strip() for item in value):
            raise ValueError("command_argv must not contain empty arguments")
        return value

    @field_validator("command_cwd")
    @classmethod
    def _validate_command_cwd(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("command_cwd must not be empty")
        return value

    @field_validator("log_path")
    @classmethod
    def _validate_log_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("log_path must not be empty")
        normalized = value.replace("\\", "/").strip()
        if "://" not in normalized and not normalized.startswith("/"):
            normalized = normalize_repository_relative_path(normalized)
        return normalized

    @field_validator("warning")
    @classmethod
    def _validate_warning(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("warning must not be empty")
        return value

    @field_validator("output_excerpt")
    @classmethod
    def _validate_output_excerpt(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("output_excerpt must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_result(self) -> "TestExecutionResult":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.success and self.status != TestExecutionStatus.PASSED:
            raise ValueError("success=True requires status=passed")
        if not self.success and self.status == TestExecutionStatus.PASSED:
            raise ValueError("status=passed requires success=True")
        if self.status == TestExecutionStatus.TIMEOUT and self.exit_code is not None:
            raise ValueError("timeout status must not include exit_code")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        source_kinds = {item.source_kind for item in self.provenance}
        if not source_kinds.intersection({SourceKind.TEST_TOOL, SourceKind.HEURISTIC}):
            raise ValueError("test execution result must include test-tool or heuristic provenance")
        return self
