from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.action_models import ActionInvocation
from suitcode.core.models import Component, FileInfo, Runner
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry
from suitcode.core.tests.models import ResolvedRelatedTest


class RunnerExecutionStatus(StrEnum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class RunnerContext(StrictModel):
    runner: Runner
    action_id: str
    provider_id: str
    invocation: ActionInvocation
    primary_component: Component | None = None
    owned_file_count: int
    owned_files_preview: tuple[FileInfo, ...]
    related_test_count: int
    related_tests_preview: tuple[ResolvedRelatedTest, ...]
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("action_id", "provider_id")
    @classmethod
    def _validate_non_empty_string(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_context(self) -> "RunnerContext":
        if self.owned_file_count < 0:
            raise ValueError("owned_file_count must be >= 0")
        if self.related_test_count < 0:
            raise ValueError("related_test_count must be >= 0")
        if self.owned_file_count < len(self.owned_files_preview):
            raise ValueError("owned_file_count must be >= len(owned_files_preview)")
        if self.related_test_count < len(self.related_tests_preview):
            raise ValueError("related_test_count must be >= len(related_tests_preview)")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class RunnerExecutionResult(StrictModel):
    runner_id: str
    action_id: str
    status: RunnerExecutionStatus
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    output_excerpt: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("runner_id", "action_id")
    @classmethod
    def _validate_non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
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

    @field_validator("output_excerpt")
    @classmethod
    def _validate_output_excerpt(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("output_excerpt must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_result(self) -> "RunnerExecutionResult":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.success and self.status != RunnerExecutionStatus.PASSED:
            raise ValueError("success=True requires status=passed")
        if not self.success and self.status == RunnerExecutionStatus.PASSED:
            raise ValueError("status=passed requires success=True")
        if self.status == RunnerExecutionStatus.TIMEOUT and self.exit_code is not None:
            raise ValueError("timeout status must not include exit_code")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self
