from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel


class EvaluationArm(StrEnum):
    SUITCODE = "suitcode"
    BASELINE = "baseline"


class SuiteRole(StrEnum):
    STABLE_READONLY = "stable_readonly"
    STABLE_EXECUTION = "stable_execution"
    STRESS_READONLY = "stress_readonly"


class ArmRunReference(StrictModel):
    arm: EvaluationArm
    suite_role: SuiteRole
    report_id: str
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int

    @field_validator("report_id")
    @classmethod
    def _validate_report_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("report_id must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_counts(self) -> "ArmRunReference":
        if any(value < 0 for value in (self.task_total, self.task_passed, self.task_failed, self.task_error)):
            raise ValueError("run reference counts must be >= 0")
        if self.task_passed + self.task_failed + self.task_error != self.task_total:
            raise ValueError("run reference counts are inconsistent")
        return self


class ComparisonDelta(StrictModel):
    metric_name: str
    suitcode_value: float | int | None
    baseline_value: float | int | None
    delta_absolute: float | None = None
    delta_ratio: float | None = None
    direction: str

    @field_validator("metric_name", "direction")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class CodexStandoutComparisonSpec(StrictModel):
    stable_readonly_tasks_file: str
    stable_execution_tasks_file: str
    stress_readonly_tasks_file: str
    passive_repository_root: str = "."
    include_stable_execution: bool = True
    include_stress_readonly: bool = True
    include_passive_usage_summary: bool = True
    stable_timeout_seconds: int | None = None
    stress_timeout_seconds: int | None = None

    @field_validator(
        "stable_readonly_tasks_file",
        "stable_execution_tasks_file",
        "stress_readonly_tasks_file",
        "passive_repository_root",
    )
    @classmethod
    def _validate_task_file(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("task file path must not be empty")
        return stripped

    @field_validator("stable_timeout_seconds", "stress_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("timeout overrides must be > 0")
        return value


class CodexStandoutReport(StrictModel):
    report_id: str
    generated_at_utc: str
    model: str | None = None
    stable_readonly_suitcode: ArmRunReference
    stable_readonly_baseline: ArmRunReference
    stable_execution_suitcode: ArmRunReference | None = None
    stress_readonly_suitcode: ArmRunReference | None = None
    headline_deltas: tuple[ComparisonDelta, ...]
    stable_readonly_summary: dict[str, object]
    stable_execution_summary: dict[str, object] | None = None
    stress_summary: dict[str, object] | None = None
    passive_usage_summary: dict[str, object] | None = None
    methodology: dict[str, object]
    limitations: tuple[str, ...] = Field(default_factory=tuple)
    repro_commands: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("report_id", "generated_at_utc")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_sections(self) -> "CodexStandoutReport":
        if not self.headline_deltas:
            raise ValueError("headline_deltas must not be empty")
        if not self.methodology:
            raise ValueError("methodology must not be empty")
        if not self.repro_commands:
            raise ValueError("repro_commands must not be empty")
        return self
