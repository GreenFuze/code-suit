from __future__ import annotations

from enum import StrEnum
from typing import Literal

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
    BUG_FIX_NAVIGATION = "bug_fix_navigation"
    CI_DEBUGGING = "ci_debugging"
    UNSUPPORTED_ACTION_REASONING = "unsupported_action_reasoning"


_DEFAULT_REQUIRED_TOOLS: dict[CodexTaskFamily, tuple[str, ...]] = {
    CodexTaskFamily.ORIENTATION: ("open_workspace", "repository_summary", "get_truth_coverage"),
    CodexTaskFamily.CHANGE_ANALYSIS: ("open_workspace", "analyze_change"),
    CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: ("open_workspace", "get_minimum_verified_change_set"),
    CodexTaskFamily.TRUTH_COVERAGE: ("open_workspace", "get_truth_coverage"),
    CodexTaskFamily.TEST_EXECUTION: ("open_workspace", "describe_test_target", "run_test_targets"),
    CodexTaskFamily.BUILD_EXECUTION: ("open_workspace", "describe_build_target", "build_target"),
    CodexTaskFamily.BUG_FIX_NAVIGATION: ("open_workspace", "get_file_owner", "get_related_tests"),
    CodexTaskFamily.CI_DEBUGGING: ("open_workspace", "get_minimum_verified_change_set"),
    CodexTaskFamily.UNSUPPORTED_ACTION_REASONING: ("open_workspace", "get_minimum_verified_change_set", "get_truth_coverage"),
}


def default_required_tools(task_family: CodexTaskFamily) -> tuple[str, ...]:
    return _DEFAULT_REQUIRED_TOOLS[task_family]


def default_high_value_tools(task_family: CodexTaskFamily) -> tuple[str, ...]:
    return tuple(
        tool for tool in default_required_tools(task_family) if tool not in {"open_workspace"}
    )


class CodexEvaluationTask(StrictModel):
    task_id: str
    repository_path: str
    task_family: CodexTaskFamily
    question: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    task_taxonomy: str | None = None
    ground_truth_kind: str | None = None
    expected_success_criteria: tuple[str, ...] = ()
    acceptable_variants: tuple[str, ...] = ()
    suite_role: str | None = None
    target_selector: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 180
    expected_required_tools: tuple[str, ...] = ()
    expected_high_value_tools: tuple[str, ...] = ()
    output_schema_id: str | None = None
    prompt_template_id: str | None = None

    @field_validator("task_id", "repository_path", "question", "task_taxonomy", "ground_truth_kind", "suite_role")
    @classmethod
    def _validate_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
        if self.question is None:
            self.question = _default_question(self.task_family, self.target_selector)
        if self.difficulty is None:
            self.difficulty = _default_difficulty(self.task_family)
        if self.task_taxonomy is None:
            self.task_taxonomy = _default_task_taxonomy(self.task_family)
        if self.ground_truth_kind is None:
            self.ground_truth_kind = _default_ground_truth_kind(self.task_family)
        if not self.expected_success_criteria:
            self.expected_success_criteria = _default_success_criteria(self.task_family)
        if self.task_family == CodexTaskFamily.TEST_EXECUTION:
            allowed = {"test_id", "repository_rel_path", "symbol_id", "owner_id"}
            if len(selector_keys & allowed) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires exactly one selector in target_selector: test_id, repository_rel_path, symbol_id, or owner_id"
                )
        if self.task_family == CodexTaskFamily.BUILD_EXECUTION:
            allowed = {"action_id", "repository_rel_path", "symbol_id", "owner_id"}
            if len(selector_keys & allowed) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires exactly one selector in target_selector: action_id, repository_rel_path, symbol_id, or owner_id"
                )
        if self.task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
            if "repository_rel_path" not in selector_keys or len(selector_keys & {"repository_rel_path"}) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires target_selector.repository_rel_path for bug_fix_navigation"
                )
        if self.task_family == CodexTaskFamily.CI_DEBUGGING:
            allowed = {"repository_rel_path", "symbol_id", "owner_id"}
            if len(selector_keys & allowed) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires exactly one selector in target_selector: repository_rel_path, symbol_id, or owner_id"
                )
        if self.task_family == CodexTaskFamily.UNSUPPORTED_ACTION_REASONING:
            allowed = {"repository_rel_path", "symbol_id", "owner_id"}
            if len(selector_keys & allowed) != 1:
                raise ValueError(
                    f"task `{self.task_id}` requires exactly one selector in target_selector: repository_rel_path, symbol_id, or owner_id"
                )
            requested_action_kind = self.target_selector.get("requested_action_kind")
            if requested_action_kind not in {"test", "build", "runner"}:
                raise ValueError(
                    f"task `{self.task_id}` requires target_selector.requested_action_kind to be one of test, build, or runner"
                )
        if not self.expected_required_tools:
            self.expected_required_tools = default_required_tools(self.task_family)
        if not self.expected_high_value_tools:
            self.expected_high_value_tools = default_high_value_tools(self.task_family)
        if self.output_schema_id is None:
            self.output_schema_id = self.task_family.value
        if self.prompt_template_id is None:
            self.prompt_template_id = self.task_family.value
        return self


def _selector_phrase(target_selector: dict[str, str]) -> str:
    if not target_selector:
        return "the repository"
    if "repository_rel_path" in target_selector:
        return target_selector["repository_rel_path"]
    if "symbol_id" in target_selector:
        return f"symbol {target_selector['symbol_id']}"
    if "owner_id" in target_selector:
        return f"owner {target_selector['owner_id']}"
    if "test_id" in target_selector:
        return f"test {target_selector['test_id']}"
    if "action_id" in target_selector:
        return f"action {target_selector['action_id']}"
    key = next(iter(target_selector))
    return f"{key}={target_selector[key]}"


def _default_question(task_family: CodexTaskFamily, target_selector: dict[str, str]) -> str:
    selector = _selector_phrase(target_selector)
    if task_family == CodexTaskFamily.ORIENTATION:
        return "What repository providers, counts, and overall truth availability describe this repository?"
    if task_family == CodexTaskFamily.CHANGE_ANALYSIS:
        return f"If {selector} changes, what is the owner, primary component, related tests, quality gates, and evidence-backed impact summary?"
    if task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
        return f"After changing {selector}, what exact deterministic validation set must run?"
    if task_family == CodexTaskFamily.TRUTH_COVERAGE:
        return "What is the repository truth coverage profile across architecture, code, tests, quality, and actions?"
    if task_family == CodexTaskFamily.TEST_EXECUTION:
        return f"Which deterministic test target should run for {selector}, and what happens when it runs?"
    if task_family == CodexTaskFamily.BUILD_EXECUTION:
        return f"Which deterministic build target should run for {selector}, and what happens when it runs?"
    if task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
        return f"A bug is reported around {selector}. What owner, dependency frontier, and related tests define the minimal debugging surface?"
    if task_family == CodexTaskFamily.CI_DEBUGGING:
        return f"CI is failing after a change touching {selector}. Which deterministic target should be inspected first?"
    requested = target_selector.get("requested_action_kind", "action")
    return f"Why can the requested {requested} action for {selector} not be resolved deterministically?"


def _default_difficulty(task_family: CodexTaskFamily) -> Literal["easy", "medium", "hard"]:
    if task_family in {CodexTaskFamily.ORIENTATION, CodexTaskFamily.TRUTH_COVERAGE}:
        return "easy"
    if task_family in {CodexTaskFamily.BUG_FIX_NAVIGATION, CodexTaskFamily.CI_DEBUGGING, CodexTaskFamily.UNSUPPORTED_ACTION_REASONING}:
        return "hard"
    return "medium"


def _default_task_taxonomy(task_family: CodexTaskFamily) -> str:
    return {
        CodexTaskFamily.ORIENTATION: "orientation",
        CodexTaskFamily.CHANGE_ANALYSIS: "impact_analysis",
        CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "minimum_verified_change_set",
        CodexTaskFamily.TRUTH_COVERAGE: "truth_coverage",
        CodexTaskFamily.TEST_EXECUTION: "test_execution",
        CodexTaskFamily.BUILD_EXECUTION: "build_execution",
        CodexTaskFamily.BUG_FIX_NAVIGATION: "bug_fix_navigation",
        CodexTaskFamily.CI_DEBUGGING: "ci_debugging",
        CodexTaskFamily.UNSUPPORTED_ACTION_REASONING: "unsupported_action_reasoning",
    }[task_family]


def _default_ground_truth_kind(task_family: CodexTaskFamily) -> str:
    return {
        CodexTaskFamily.ORIENTATION: "exact_field_match",
        CodexTaskFamily.CHANGE_ANALYSIS: "exact_field_match",
        CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "exact_id_set_match",
        CodexTaskFamily.TRUTH_COVERAGE: "exact_field_match",
        CodexTaskFamily.TEST_EXECUTION: "exact_action_target_match",
        CodexTaskFamily.BUILD_EXECUTION: "exact_action_target_match",
        CodexTaskFamily.BUG_FIX_NAVIGATION: "exact_field_match",
        CodexTaskFamily.CI_DEBUGGING: "exact_field_match",
        CodexTaskFamily.UNSUPPORTED_ACTION_REASONING: "exact_field_match",
    }[task_family]


def _default_success_criteria(task_family: CodexTaskFamily) -> tuple[str, ...]:
    if task_family == CodexTaskFamily.ORIENTATION:
        return (
            "provider_ids match deterministic baseline",
            "component_count matches deterministic baseline",
            "test_count matches deterministic baseline",
            "quality_provider_count matches deterministic baseline",
            "overall_truth_availability matches deterministic baseline",
        )
    if task_family == CodexTaskFamily.CHANGE_ANALYSIS:
        return (
            "owner_id matches deterministic baseline",
            "primary_component_id matches deterministic baseline",
            "related_test_ids match deterministic baseline",
            "quality_gate_provider_ids match deterministic baseline",
            "evidence_edge_count matches deterministic baseline",
            "overall_truth_availability matches deterministic baseline",
        )
    if task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
        return (
            "owner_id matches deterministic baseline",
            "primary_component_id matches deterministic baseline",
            "test_target_ids match deterministic baseline exactly",
            "build_target_ids match deterministic baseline exactly",
            "runner_action_ids match deterministic baseline exactly",
            "quality_validation_operation_ids match deterministic baseline exactly",
            "quality_hygiene_operation_ids match deterministic baseline exactly",
        )
    if task_family == CodexTaskFamily.TRUTH_COVERAGE:
        return (
            "overall_availability matches deterministic baseline",
            "per-domain availability matches deterministic baseline",
            "per-domain authoritative_count matches deterministic baseline",
            "per-domain derived_count matches deterministic baseline",
            "per-domain heuristic_count matches deterministic baseline",
            "per-domain unavailable_count matches deterministic baseline",
        )
    if task_family == CodexTaskFamily.TEST_EXECUTION:
        return (
            "selected_test_id matches deterministic baseline target",
            "command_preview matches deterministic baseline describe_test_target output",
            "execution_status matches deterministic baseline",
            "passed/failed/errors/timeouts match deterministic baseline",
        )
    if task_family == CodexTaskFamily.BUILD_EXECUTION:
        return (
            "selected_action_id matches deterministic baseline target",
            "command_preview matches deterministic baseline describe_build_target output",
            "execution_status matches deterministic baseline",
            "succeeded matches deterministic baseline",
        )
    if task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
        return (
            "owner_id matches deterministic baseline",
            "owner_kind matches deterministic baseline",
            "related_test_ids_preview matches deterministic baseline",
            "related_test_count matches deterministic baseline",
        )
    if task_family == CodexTaskFamily.CI_DEBUGGING:
        return (
            "owner_id matches deterministic baseline",
            "primary_component_id matches deterministic baseline",
            "recommended_action_kind matches deterministic baseline",
            "recommended_target_id matches deterministic baseline",
            "command_preview matches deterministic baseline",
            "target_source_tool matches deterministic baseline",
        )
    return (
        "requested_action_kind matches the task selector exactly",
        "supported matches deterministic baseline",
        "available_action_kinds match deterministic baseline",
        "overall_truth_availability matches deterministic baseline",
        "actions_availability matches deterministic baseline",
        "reason_code matches deterministic baseline",
    )
