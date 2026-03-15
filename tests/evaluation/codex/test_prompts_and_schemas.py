from __future__ import annotations

from pathlib import Path

from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.output_schemas import schema_for_family
from suitcode.evaluation.codex.prompts import CodexPromptLibrary
from suitcode.evaluation.codex.task_contracts import contract_for
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily


def test_prompt_library_is_neutral_across_arms_and_includes_task_metadata(tmp_path: Path) -> None:
    task = CodexEvaluationTask(
        task_id="change-1",
        repository_path=".",
        task_family=CodexTaskFamily.CHANGE_ANALYSIS,
        target_selector={"repository_rel_path": "src/app.py"},
        question="If src/app.py changes, what is the deterministic impact summary?",
        task_taxonomy="impact_analysis",
        difficulty="medium",
        ground_truth_kind="exact_field_match",
        expected_success_criteria=("owner matches baseline", "tests match baseline"),
    )

    suitcode_prompt = CodexPromptLibrary().build_prompt(task, repository_root=tmp_path, arm=EvaluationArm.SUITCODE)
    baseline_prompt = CodexPromptLibrary().build_prompt(task, repository_root=tmp_path, arm=EvaluationArm.BASELINE)

    assert "Question: If src/app.py changes, what is the deterministic impact summary?" in suitcode_prompt
    assert "- repository_rel_path: src/app.py" in suitcode_prompt
    assert "Stay within" not in suitcode_prompt  # ensure exact phrasing not accidentally duplicated from old prompts
    assert "Repository root constraint" in suitcode_prompt
    assert "Return only a JSON object" in suitcode_prompt
    assert "Do not fabricate values" in suitcode_prompt
    assert "one tool call at a time" in suitcode_prompt
    assert "SuitCode may be available in this environment." in suitcode_prompt
    assert "Some external tools may be unavailable in this environment" in baseline_prompt
    assert "Call open_workspace" not in suitcode_prompt
    assert "analyze_change" not in suitcode_prompt
    assert "Do not use shell commands" not in suitcode_prompt
    assert "Do not use SuitCode" not in baseline_prompt


def test_orientation_contract_expected_arguments_match_baseline() -> None:
    contract = contract_for(CodexTaskFamily.ORIENTATION)
    task = CodexEvaluationTask(task_id="orientation-1", repository_path=".", task_family=CodexTaskFamily.ORIENTATION)

    expected = contract.expected_argument_subsets(task, workspace_id="workspace:demo", repository_id="repo:demo")

    assert expected == (
        ("repository_summary", {"workspace_id": "workspace:demo", "repository_id": "repo:demo"}),
        ("get_truth_coverage", {"workspace_id": "workspace:demo", "repository_id": "repo:demo"}),
    )


def test_output_schema_contains_expected_properties() -> None:
    schema = schema_for_family(CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET)

    properties = schema.get("properties", {})
    assert "owner_id" in properties
    assert "test_target_ids" in properties
    assert "quality_hygiene_operation_ids" in properties
    assert set(schema.get("required", [])) == set(properties)


def test_v7_prompt_can_include_auto_orientation_hint() -> None:
    task = CodexEvaluationTask(
        task_id="ci-debug-1",
        repository_path=".",
        task_family=CodexTaskFamily.CI_DEBUGGING,
        target_selector={"repository_rel_path": "src/app.py"},
    )

    prompt = CodexPromptLibrary().build_prompt(
        task,
        repository_root=Path("/tmp/repo"),
        arm=EvaluationArm.SUITCODE,
        auto_orientation_hint=True,
    )

    assert "deterministic repository-intelligence or validation-surface tool" in prompt
    assert "Task family: ci_debugging" in prompt


def test_v7_output_schema_contains_new_family_properties() -> None:
    schema = schema_for_family(CodexTaskFamily.UNSUPPORTED_ACTION_REASONING)

    properties = schema.get("properties", {})
    assert "requested_action_kind" in properties
    assert "available_action_kinds" in properties
    assert "reason_code" in properties
