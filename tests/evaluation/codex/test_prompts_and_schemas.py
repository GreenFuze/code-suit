from __future__ import annotations

from pathlib import Path

from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.task_contracts import contract_for
from suitcode.evaluation.codex.output_schemas import schema_for_family
from suitcode.evaluation.codex.prompts import CodexPromptLibrary
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily


def test_prompt_library_includes_required_flow_and_selector(tmp_path: Path) -> None:
    task = CodexEvaluationTask(
        task_id="change-1",
        repository_path=".",
        task_family=CodexTaskFamily.CHANGE_ANALYSIS,
        target_selector={"repository_rel_path": "src/app.py"},
    )

    prompt = CodexPromptLibrary().build_prompt(task, repository_root=tmp_path)

    assert "analyze_change" in prompt
    assert "repository_rel_path: src/app.py" in prompt
    assert "Do not use shell commands" in prompt
    assert "Call open_workspace" in prompt
    assert "Make exactly one tool call at a time" in prompt
    assert "Do not call update_plan" in prompt
    assert "Return only a JSON object" in prompt


def test_orientation_prompt_includes_preview_limit_and_exact_copying(tmp_path: Path) -> None:
    task = CodexEvaluationTask(
        task_id="orientation-1",
        repository_path=".",
        task_family=CodexTaskFamily.ORIENTATION,
    )

    prompt = CodexPromptLibrary().build_prompt(task, repository_root=tmp_path)

    assert "preview_limit set to 8" in prompt
    assert "Do not infer repository_summary fields from get_truth_coverage" in prompt


def test_baseline_prompt_excludes_suitcode_and_allows_direct_exploration(tmp_path: Path) -> None:
    task = CodexEvaluationTask(
        task_id="truth-1",
        repository_path=".",
        task_family=CodexTaskFamily.TRUTH_COVERAGE,
    )

    prompt = CodexPromptLibrary().build_prompt(task, repository_root=tmp_path, arm=EvaluationArm.BASELINE)

    assert "Do not use SuitCode" in prompt
    assert "Use direct filesystem, manifest, search, and shell evidence" in prompt
    assert "mcp__suitcode__" not in prompt
    assert "Return only a JSON object" in prompt


def test_task_contract_expected_arguments_match_orientation_baseline() -> None:
    contract = contract_for(CodexTaskFamily.ORIENTATION)
    task = CodexEvaluationTask(task_id="orientation-1", repository_path=".", task_family=CodexTaskFamily.ORIENTATION)

    expected = contract.expected_argument_subsets(task, workspace_id="workspace:demo", repository_id="repo:demo")

    assert expected == (
        ("repository_summary", {"workspace_id": "workspace:demo", "repository_id": "repo:demo", "preview_limit": 8}),
        ("get_truth_coverage", {"workspace_id": "workspace:demo", "repository_id": "repo:demo"}),
    )


def test_output_schema_contains_expected_properties() -> None:
    schema = schema_for_family(CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET)

    properties = schema.get("properties", {})
    assert "owner_id" in properties
    assert "test_target_ids" in properties
    assert "quality_hygiene_operation_ids" in properties
    assert set(schema.get("required", [])) == set(properties)
