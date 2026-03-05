from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel


class ActionExecutionStatus(StrEnum):
    __test__ = False
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class ActionExecutionResult(StrictModel):
    action_id: str
    status: ActionExecutionStatus
    success: bool
    command_argv: tuple[str, ...]
    command_cwd: str | None = None
    exit_code: int | None = None
    duration_ms: int
    log_path: str
    output_excerpt: str | None = None
    output: str

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action_id must not be empty")
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

    @field_validator("output")
    @classmethod
    def _validate_output(cls, value: str) -> str:
        return value

    @model_validator(mode="after")
    def _validate_result(self) -> "ActionExecutionResult":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.success and self.status != ActionExecutionStatus.PASSED:
            raise ValueError("success=True requires status=passed")
        if not self.success and self.status == ActionExecutionStatus.PASSED:
            raise ValueError("status=passed requires success=True")
        if self.status == ActionExecutionStatus.TIMEOUT and self.exit_code is not None:
            raise ValueError("timeout status must not include exit_code")
        return self
