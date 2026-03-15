from __future__ import annotations

from typing import Literal

from pydantic import Field

from suitcode.analytics.models import StrictModel
from suitcode.evaluation.codex.task_models import CodexTaskFamily


AvailabilityLiteral = Literal["available", "degraded", "unavailable"]


class DomainAvailabilityModel(StrictModel):
    availability: AvailabilityLiteral = Field(
        description=(
            "Copy the domain availability exactly from get_truth_coverage for this same domain. "
            "Allowed values are available, degraded, or unavailable. Do not infer or normalize."
        )
    )
    authoritative_count: int = Field(
        ge=0,
        description=(
            "Copy authoritative_count exactly from get_truth_coverage for this same domain. "
            "Do not use 0 unless the tool output is actually 0."
        ),
    )
    derived_count: int = Field(
        ge=0,
        description=(
            "Copy derived_count exactly from get_truth_coverage for this same domain. "
            "Do not use 0 unless the tool output is actually 0."
        ),
    )
    heuristic_count: int = Field(
        ge=0,
        description=(
            "Copy heuristic_count exactly from get_truth_coverage for this same domain. "
            "Do not use 0 unless the tool output is actually 0."
        ),
    )
    unavailable_count: int = Field(
        ge=0,
        description=(
            "Copy unavailable_count exactly from get_truth_coverage for this same domain. "
            "Do not use 0 unless the tool output is actually 0."
        ),
    )


class OrientationOutputModel(StrictModel):
    workspace_id: str = Field(description="The workspace_id returned by open_workspace.")
    repository_id: str = Field(description="The repository_id returned by open_workspace.")
    provider_ids: tuple[str, ...] = Field(description="Copy provider_ids exactly from repository_summary.")
    component_count: int = Field(description="Copy component_count exactly from repository_summary.")
    test_count: int = Field(description="Copy test_count exactly from repository_summary.")
    quality_provider_count: int = Field(description="Copy the number of quality providers exactly from repository_summary.")
    overall_truth_availability: str = Field(description="Copy overall_availability exactly from get_truth_coverage.")


class ChangeAnalysisOutputModel(StrictModel):
    target_kind: str = Field(description="Copy target_kind exactly from analyze_change.")
    owner_id: str = Field(description="Copy owner.id exactly from analyze_change.")
    primary_component_id: str | None = Field(default=None, description="Copy primary_component.id exactly from analyze_change, or null.")
    related_test_ids: tuple[str, ...] = Field(description="Copy related test IDs exactly from analyze_change.")
    quality_gate_provider_ids: tuple[str, ...] = Field(description="Copy quality gate provider IDs exactly from analyze_change.")
    evidence_edge_count: int = Field(description="Copy evidence.total_edges exactly from analyze_change.")
    overall_truth_availability: str = Field(description="Copy truth_coverage.overall_availability exactly from analyze_change.")


class MinimumVerifiedOutputModel(StrictModel):
    owner_id: str = Field(description="Copy owner.id exactly from get_minimum_verified_change_set.")
    primary_component_id: str | None = Field(default=None, description="Copy primary_component.id exactly from get_minimum_verified_change_set, or null.")
    test_target_ids: tuple[str, ...] = Field(description="Copy test target IDs exactly from get_minimum_verified_change_set.")
    build_target_ids: tuple[str, ...] = Field(description="Copy build target IDs exactly from get_minimum_verified_change_set.")
    runner_action_ids: tuple[str, ...] = Field(description="Copy runner action IDs exactly from get_minimum_verified_change_set.")
    quality_validation_operation_ids: tuple[str, ...] = Field(description="Copy quality validation operation IDs exactly from get_minimum_verified_change_set.")
    quality_hygiene_operation_ids: tuple[str, ...] = Field(description="Copy quality hygiene operation IDs exactly from get_minimum_verified_change_set.")


class TruthCoverageOutputModel(StrictModel):
    overall_availability: AvailabilityLiteral = Field(
        description=(
            "Copy overall_availability exactly from get_truth_coverage. "
            "Do not infer, summarize, or fall back to unavailable unless the tool output says unavailable."
        )
    )
    architecture: DomainAvailabilityModel
    code: DomainAvailabilityModel
    tests: DomainAvailabilityModel
    quality: DomainAvailabilityModel
    actions: DomainAvailabilityModel


class TestExecutionOutputModel(StrictModel):
    selected_test_id: str = Field(description="Copy the selected test ID exactly from the deterministic test target used.")
    command_preview: tuple[str, ...] = Field(description="Copy the describe_test_target command exactly.")
    execution_status: str = Field(description="Copy the execution status exactly from the test run result.")
    passed: int = Field(description="Copy passed exactly from the test run result.")
    failed: int = Field(description="Copy failed exactly from the test run result.")
    errors: int = Field(description="Copy errors exactly from the test run result.")
    timeouts: int = Field(description="Copy timeouts exactly from the test run result.")


class BuildExecutionOutputModel(StrictModel):
    selected_action_id: str = Field(description="Copy the selected build action ID exactly from the deterministic build target used.")
    command_preview: tuple[str, ...] = Field(description="Copy the describe_build_target command exactly.")
    execution_status: str = Field(description="Copy the execution status exactly from the build result.")
    succeeded: bool = Field(description="Copy success exactly from the build result.")


class BugFixNavigationOutputModel(StrictModel):
    owner_id: str = Field(description="Copy owner.id exactly from get_file_owner.")
    owner_kind: str = Field(description="Copy owner.kind exactly from get_file_owner.")
    related_test_ids_preview: tuple[str, ...] = Field(description="Copy the sorted related test IDs exactly from get_related_tests.")
    related_test_count: int = Field(description="Copy total exactly from get_related_tests.")


class CiDebuggingOutputModel(StrictModel):
    owner_id: str = Field(description="Copy owner.id exactly from the deterministic baseline used for CI debugging.")
    primary_component_id: str | None = Field(default=None, description="Copy primary_component.id exactly from get_minimum_verified_change_set, or null.")
    recommended_action_kind: str = Field(description="Copy whether the chosen deterministic target is a test or build action.")
    recommended_target_id: str = Field(description="Copy the chosen deterministic target ID exactly.")
    command_preview: tuple[str, ...] = Field(description="Copy the describe_* command preview exactly for the chosen target.")
    target_source_tool: str = Field(description="Copy the deterministic source tool used to describe the chosen target, such as describe_test_target or describe_build_target.")


class UnsupportedActionReasoningOutputModel(StrictModel):
    requested_action_kind: str = Field(description="Copy the requested action kind exactly from the task selector.")
    supported: bool = Field(description="Report whether a deterministic target exists for the requested action kind.")
    available_action_kinds: tuple[str, ...] = Field(description="Copy the sorted set of deterministic action kinds available from get_minimum_verified_change_set.")
    overall_truth_availability: AvailabilityLiteral = Field(description="Copy overall_availability exactly from get_truth_coverage.")
    actions_availability: AvailabilityLiteral = Field(description="Copy actions.availability exactly from get_truth_coverage.")
    reason_code: str = Field(description="Copy the deterministic support classification exactly: available, actions_truth_unavailable, requested_kind_not_in_minimum_verified_set, or no_deterministic_actions_available.")


_OUTPUT_MODELS = {
    CodexTaskFamily.ORIENTATION: OrientationOutputModel,
    CodexTaskFamily.CHANGE_ANALYSIS: ChangeAnalysisOutputModel,
    CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: MinimumVerifiedOutputModel,
    CodexTaskFamily.TRUTH_COVERAGE: TruthCoverageOutputModel,
    CodexTaskFamily.TEST_EXECUTION: TestExecutionOutputModel,
    CodexTaskFamily.BUILD_EXECUTION: BuildExecutionOutputModel,
    CodexTaskFamily.BUG_FIX_NAVIGATION: BugFixNavigationOutputModel,
    CodexTaskFamily.CI_DEBUGGING: CiDebuggingOutputModel,
    CodexTaskFamily.UNSUPPORTED_ACTION_REASONING: UnsupportedActionReasoningOutputModel,
}


def model_for_family(task_family: CodexTaskFamily):
    return _OUTPUT_MODELS[task_family]


def schema_for_family(task_family: CodexTaskFamily) -> dict[str, object]:
    schema = model_for_family(task_family).model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties.keys())
    return schema
