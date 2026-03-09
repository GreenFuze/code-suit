from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel


class CodexTaskFamily(StrEnum):
    __test__ = False
    ORIENTATION = "orientation"
    CHANGE_ANALYSIS = "change_analysis"
    MINIMUM_VERIFIED_CHANGE_SET = "minimum_verified_change_set"
    TRUTH_COVERAGE = "truth_coverage"
    TEST_EXECUTION = "test_execution"
    BUILD_EXECUTION = "build_execution"


_DEFAULT_REQUIRED_TOOLS: dict[CodexTaskFamily, tuple[str, ...]] = {
    CodexTaskFamily.ORIENTATION: ("open_workspace", "repository_summary", "get_truth_coverage"),
    CodexTaskFamily.CHANGE_ANALYSIS: ("open_workspace", "analyze_change"),
    CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: ("open_workspace", "get_minimum_verified_change_set"),
    CodexTaskFamily.TRUTH_COVERAGE: ("open_workspace", "get_truth_coverage"),
    CodexTaskFamily.TEST_EXECUTION: ("open_workspace", "list_tests", "describe_test_target", "run_test_targets"),
    CodexTaskFamily.BUILD_EXECUTION: ("open_workspace", "list_build_targets", "describe_build_target", "build_target"),
}


def default_required_tools(task_family: CodexTaskFamily) -> tuple[str, ...]:
    return _DEFAULT_REQUIRED_TOOLS[task_family]


def default_high_value_tools(task_family: CodexTaskFamily) -> tuple[str, ...]:
    return tuple(
        tool for tool in default_required_tools(task_family) if tool not in {"open_workspace", "list_tests", "list_build_targets"}
    )


class CodexEvaluationTask(StrictModel):
    task_id: str
    repository_path: str
    task_family: CodexTaskFamily
    target_selector: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 180
    expected_required_tools: tuple[str, ...] = ()
    expected_high_value_tools: tuple[str, ...] = ()
    output_schema_id: str | None = None
    prompt_template_id: str | None = None

    @field_validator("task_id", "repository_path")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value.strip()

    @model_validator(mode="after")
    def _validate_task(self) -> "CodexEvaluationTask":
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        selector_keys = {key for key, value in self.target_selector.items() if isinstance(value, str) and value.strip()}
        if self.task_family in {CodexTaskFamily.CHANGE_ANALYSIS, CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET}:
            target_keys = {"symbol_id", "repository_rel_path", "owner_id"}
            if len(selector_keys & target_keys) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires exactly one selector in target_selector: symbol_id, repository_rel_path, or owner_id"
                )
        if self.task_family == CodexTaskFamily.TEST_EXECUTION and "test_id" in selector_keys and "test_id" not in self.target_selector:
            raise ValueError("invalid test_id selector")
        if self.task_family == CodexTaskFamily.BUILD_EXECUTION and "action_id" in selector_keys and "action_id" not in self.target_selector:
            raise ValueError("invalid action_id selector")
        if not self.expected_required_tools:
            self.expected_required_tools = default_required_tools(self.task_family)
        if not self.expected_high_value_tools:
            self.expected_high_value_tools = default_high_value_tools(self.task_family)
        if self.output_schema_id is None:
            self.output_schema_id = self.task_family.value
        if self.prompt_template_id is None:
            self.prompt_template_id = self.task_family.value
        return self
