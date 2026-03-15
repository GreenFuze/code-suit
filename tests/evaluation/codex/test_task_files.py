from __future__ import annotations

import json
from pathlib import Path

from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily


def _load_tasks(path: str) -> tuple[CodexEvaluationTask, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(CodexEvaluationTask.model_validate(item) for item in payload)


def test_smoke_task_file_contains_fast_truth_coverage_tasks() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_smoke.json")

    assert len(tasks) == 2
    assert {task.task_family for task in tasks} == {CodexTaskFamily.TRUTH_COVERAGE}
    assert {task.repository_path for task in tasks} == {"tests/test_repos/python", "tests/test_repos/npm"}
    assert all(task.timeout_seconds <= 180 for task in tasks)


def test_v6_headline_task_file_contains_only_downstream_ab_tasks() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_v6_headline.json")

    assert len(tasks) == 4
    assert {task.task_family for task in tasks} == {
        CodexTaskFamily.CHANGE_ANALYSIS,
        CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET,
    }
    assert {task.repository_path for task in tasks if task.task_id.startswith("project-")} == {"."}
    assert {task.repository_path for task in tasks if task.task_id.startswith("fixture-npm-")} == {"tests/test_repos/npm"}
    assert {
        task.target_selector.get("repository_rel_path")
        for task in tasks
        if task.task_id.startswith("project-python-")
    } == {"src/suitcode/mcp/descriptions.py", "src/suitcode/mcp/service.py"}
    assert {
        task.target_selector.get("repository_rel_path")
        for task in tasks
        if task.task_id.startswith("fixture-npm-")
    } == {"packages/core/src/index.ts"}
    assert {task.difficulty for task in tasks} == {"medium"}
    assert {task.suite_role for task in tasks} == {"headline_ab"}


def test_v6_calibration_task_file_contains_orientation_and_truth_coverage_only() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_calibration.json")

    assert len(tasks) == 4
    assert {task.task_family for task in tasks} == {
        CodexTaskFamily.ORIENTATION,
        CodexTaskFamily.TRUTH_COVERAGE,
    }
    assert {task.repository_path for task in tasks if task.task_id.startswith("project-")} == {"."}
    assert {task.repository_path for task in tasks if task.task_id.startswith("fixture-npm-")} == {"tests/test_repos/npm"}
    assert {task.suite_role for task in tasks} == {"calibration"}


def test_project_readonly_task_file_preserves_live_project_stress_suite() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_project_readonly.json")

    assert len(tasks) == 8
    assert {task.repository_path for task in tasks if task.task_id.startswith("python-")} == {"."}
    assert {task.repository_path for task in tasks if task.task_id.startswith("npm-")} == {"tests/test_repos/npm"}
    assert {
        task.target_selector.get("repository_rel_path")
        for task in tasks
        if task.task_id in {"python-change-analysis", "python-minimum-verified"}
    } == {"src/suitcode/mcp/service.py"}


def test_execution_ab_task_file_contains_selector_driven_execution_tasks() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_execution_ab.json")

    assert len(tasks) == 2
    assert {task.task_id for task in tasks} == {"fixture-python-test-execution", "fixture-npm-build-execution"}
    assert {task.repository_path for task in tasks} == {"tests/test_repos/python", "tests/test_repos/npm"}
    assert {task.timeout_seconds for task in tasks} == {300}
    assert next(task for task in tasks if task.task_id == "fixture-python-test-execution").target_selector == {
        "repository_rel_path": "src/acme/core/repository.py"
    }
    assert next(task for task in tasks if task.task_id == "fixture-npm-build-execution").target_selector == {
        "repository_rel_path": "tools/codegen/main.py"
    }


def test_v7_headline_task_file_contains_new_downstream_task_families() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_v7_headline.json")

    assert len(tasks) == 5
    assert {task.task_family for task in tasks} == {
        CodexTaskFamily.BUG_FIX_NAVIGATION,
        CodexTaskFamily.UNSUPPORTED_ACTION_REASONING,
        CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET,
    }
    assert {task.repository_path for task in tasks if task.task_id.startswith("project-")} == {"."}
    assert {task.repository_path for task in tasks if task.task_id.startswith("fixture-npm-")} == {"tests/test_repos/npm"}
    assert {task.suite_role for task in tasks} == {"headline_ab"}
    assert {task.difficulty for task in tasks} == {"hard", "medium"}


def test_v7_adoption_task_file_contains_bug_fix_and_ci_debugging_tasks() -> None:
    tasks = _load_tasks("benchmarks/codex/tasks/suitcode_v7_adoption_latency.json")

    assert len(tasks) == 4
    assert {task.task_family for task in tasks} == {
        CodexTaskFamily.BUG_FIX_NAVIGATION,
        CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET,
        CodexTaskFamily.UNSUPPORTED_ACTION_REASONING,
    }
    assert {task.suite_role for task in tasks} == {"adoption_experiment"}
