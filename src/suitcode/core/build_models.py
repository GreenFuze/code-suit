from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.core.action_models import ActionInvocation, ActionTargetKind
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry
from suitcode.core.validation import validate_timeout_seconds


class BuildExecutionStatus(StrEnum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class BuildTargetDescription(StrictModel):
    action_id: str
    name: str
    provider_id: str
    target_id: str
    target_kind: ActionTargetKind
    owner_ids: tuple[str, ...] = Field(default_factory=tuple)
    invocation: ActionInvocation
    dry_run_supported: bool = False
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_target(self) -> "BuildTargetDescription":
        if not self.action_id.strip():
            raise ValueError("action_id must not be empty")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if not self.target_id.strip():
            raise ValueError("target_id must not be empty")
        if self.target_kind not in {ActionTargetKind.COMPONENT, ActionTargetKind.REPOSITORY}:
            raise ValueError("build target_kind must be `component` or `repository`")
        if any(not owner_id.strip() for owner_id in self.owner_ids):
            raise ValueError("owner_ids must not contain empty values")
        if len(set(self.owner_ids)) != len(self.owner_ids):
            raise ValueError("owner_ids must not contain duplicates")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class BuildExecutionResult(StrictModel):
    action_id: str
    target_id: str
    target_kind: ActionTargetKind
    status: BuildExecutionStatus
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    output_excerpt: str | None = None
    provenance: tuple[ProvenanceEntry, ...]

    @field_validator("action_id", "target_id")
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
    def _validate_result(self) -> "BuildExecutionResult":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.success and self.status != BuildExecutionStatus.PASSED:
            raise ValueError("success=True requires status=passed")
        if not self.success and self.status == BuildExecutionStatus.PASSED:
            raise ValueError("status=passed requires success=True")
        if self.status == BuildExecutionStatus.TIMEOUT and self.exit_code is not None:
            raise ValueError("timeout status must not include exit_code")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class BuildProjectResult(StrictModel):
    timeout_seconds: int
    total: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    succeeded_target_ids: tuple[str, ...] = Field(default_factory=tuple)
    failed_results: tuple[BuildExecutionResult, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_summary(self) -> "BuildProjectResult":
        validate_timeout_seconds(self.timeout_seconds)
        for field_name in ("total", "passed", "failed", "errors", "timeouts"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if self.total != self.passed + self.failed + self.errors + self.timeouts:
            raise ValueError("total must equal passed + failed + errors + timeouts")
        if self.passed != len(self.succeeded_target_ids):
            raise ValueError("passed must equal len(succeeded_target_ids)")
        if self.failed + self.errors + self.timeouts != len(self.failed_results):
            raise ValueError("failed + errors + timeouts must equal len(failed_results)")
        if any(not item.strip() for item in self.succeeded_target_ids):
            raise ValueError("succeeded_target_ids must not contain empty values")
        if len(set(self.succeeded_target_ids)) != len(self.succeeded_target_ids):
            raise ValueError("succeeded_target_ids must not contain duplicates")
        if any(item.status == BuildExecutionStatus.PASSED for item in self.failed_results):
            raise ValueError("failed_results must not contain passed statuses")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self
