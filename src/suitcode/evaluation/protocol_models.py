from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel


class MetricKind(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    DERIVED = "derived"


class TaskTaxonomy(StrEnum):
    ORIENTATION = "orientation"
    LOCALIZATION = "localization"
    IMPACT_ANALYSIS = "impact_analysis"
    BUG_FIX_NAVIGATION = "bug_fix_navigation"
    CI_DEBUGGING = "ci_debugging"
    MINIMUM_VERIFIED_CHANGE_SET = "minimum_verified_change_set"
    TRUTH_COVERAGE = "truth_coverage"
    UNSUPPORTED_ACTION_REASONING = "unsupported_action_reasoning"
    TEST_SELECTION = "test_selection"
    TEST_EXECUTION = "test_execution"
    BUILD_SELECTION = "build_selection"
    BUILD_EXECUTION = "build_execution"
    QUALITY = "quality"
    RUNNER_EXECUTION = "runner_execution"


class GroundTruthKind(StrEnum):
    EXACT_FIELD_MATCH = "exact_field_match"
    EXACT_ID_SET_MATCH = "exact_id_set_match"
    EXACT_ACTION_TARGET_MATCH = "exact_action_target_match"
    EXACT_ACTION_RESULT_MATCH = "exact_action_result_match"
    PROVENANCE_PRESENCE_MATCH = "provenance_presence_match"


class RunTemperature(StrEnum):
    COLD = "cold"
    WARM = "warm"


class MetricDefinition(StrictModel):
    metric_name: str
    metric_kind: MetricKind
    unit: str
    description: str
    reported_in_headline: bool
    is_primary: bool

    @field_validator("metric_name", "unit", "description")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class TaskProtocol(StrictModel):
    task_id: str
    task_family: str
    task_taxonomy: TaskTaxonomy
    repository_path: str
    difficulty: str
    run_temperature: RunTemperature
    question: str
    target_selector: dict[str, str] = Field(default_factory=dict)
    required_tools: tuple[str, ...]
    expected_ground_truth_kind: GroundTruthKind
    expected_success_criteria: tuple[str, ...]
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("task_id", "task_family", "repository_path", "difficulty", "question")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_success_criteria(self) -> "TaskProtocol":
        if not self.required_tools:
            raise ValueError("required_tools must not be empty")
        if not self.expected_success_criteria:
            raise ValueError("expected_success_criteria must not be empty")
        return self


class BenchmarkCondition(StrictModel):
    name: str
    arm: str
    native_agent_tools: tuple[str, ...]
    suitcode_enabled: bool
    suitcode_tools_available: bool
    prompt_policy: str
    sandbox_mode: str | None
    approval_mode: str | None
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("name", "arm", "prompt_policy", "sandbox_mode", "approval_mode")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_tools(self) -> "BenchmarkCondition":
        if not self.native_agent_tools:
            raise ValueError("native_agent_tools must not be empty")
        return self


class RepositoryProfile(StrictModel):
    repository_path: str
    ecosystem: str
    language_hint: str
    approximate_file_count: int | None = None
    component_count: int | None = None
    test_count: int | None = None
    deterministic_action_count: int | None = None
    test_action_count: int | None = None
    build_action_count: int | None = None
    runner_action_count: int | None = None
    build_tool: str | None = None
    repository_shape: str | None = None
    architecture_basis: str
    test_discovery_basis: str
    quality_basis: str
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator(
        "repository_path",
        "ecosystem",
        "language_hint",
        "repository_shape",
        "build_tool",
        "architecture_basis",
        "test_discovery_basis",
        "quality_basis",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator(
        "approximate_file_count",
        "component_count",
        "test_count",
        "deterministic_action_count",
        "test_action_count",
        "build_action_count",
        "runner_action_count",
    )
    @classmethod
    def _validate_counts(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("counts must be >= 0")
        return value


class BenchmarkProtocol(StrictModel):
    protocol_name: str
    agent_family: str
    agent_version: str | None = None
    model_name: str | None = None
    model_provider: str | None = None
    conditions: tuple[BenchmarkCondition, ...]
    task_protocols: tuple[TaskProtocol, ...]
    repository_profiles: tuple[RepositoryProfile, ...]
    metric_definitions: tuple[MetricDefinition, ...]
    timeout_policy: str
    session_policy: str
    cache_policy: str
    repo_state_policy: str
    hardware_os_notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator(
        "protocol_name",
        "agent_family",
        "agent_version",
        "model_name",
        "model_provider",
        "timeout_policy",
        "session_policy",
        "cache_policy",
        "repo_state_policy",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_sections(self) -> "BenchmarkProtocol":
        if len(self.conditions) < 2:
            raise ValueError("conditions must include at least baseline and treatment")
        if not self.task_protocols:
            raise ValueError("task_protocols must not be empty")
        if not self.repository_profiles:
            raise ValueError("repository_profiles must not be empty")
        if not self.metric_definitions:
            raise ValueError("metric_definitions must not be empty")
        known_repositories = {item.repository_path for item in self.repository_profiles}
        for task in self.task_protocols:
            if task.repository_path not in known_repositories:
                raise ValueError("each task_protocol must map to a repository_profile")
        return self
