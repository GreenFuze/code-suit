from __future__ import annotations

import json
from pathlib import Path

from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily


def test_smoke_task_file_contains_fast_truth_coverage_tasks() -> None:
    task_file = Path("benchmarks/codex/tasks/suitcode_smoke.json")
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    assert len(tasks) == 2
    assert {task.task_family for task in tasks} == {CodexTaskFamily.TRUTH_COVERAGE}
    assert {task.repository_path for task in tasks} == {"tests/test_repos/python", "tests/test_repos/npm"}
    assert all(task.timeout_seconds <= 180 for task in tasks)


def test_readonly_task_file_contains_expected_read_only_tasks() -> None:
    task_file = Path("benchmarks/codex/tasks/suitcode_readonly.json")
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    assert len(tasks) == 8
    assert {task.task_id for task in tasks} == {
        "python-orientation",
        "python-change-analysis",
        "python-minimum-verified",
        "python-truth-coverage",
        "npm-orientation",
        "npm-change-analysis",
        "npm-minimum-verified",
        "npm-truth-coverage",
    }
    assert {task.repository_path for task in tasks if task.task_id.startswith("python-")} == {"tests/test_repos/python"}
    assert {task.repository_path for task in tasks if task.task_id.startswith("npm-")} == {"tests/test_repos/npm"}
    assert {
        task.target_selector.get("repository_rel_path")
        for task in tasks
        if task.task_id in {"python-change-analysis", "python-minimum-verified"}
    } == {"src/acme/core/repository.py"}
    assert all(task.timeout_seconds == 180 for task in tasks if task.task_family == CodexTaskFamily.TRUTH_COVERAGE)
    assert all(task.timeout_seconds == 240 for task in tasks if task.task_family != CodexTaskFamily.TRUTH_COVERAGE)


def test_project_readonly_task_file_preserves_live_project_stress_suite() -> None:
    task_file = Path("benchmarks/codex/tasks/suitcode_project_readonly.json")
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    assert len(tasks) == 8
    assert {task.repository_path for task in tasks if task.task_id.startswith("python-")} == {"."}
    assert {task.repository_path for task in tasks if task.task_id.startswith("npm-")} == {"tests/test_repos/npm"}
    assert {
        task.target_selector.get("repository_rel_path")
        for task in tasks
        if task.task_id in {"python-change-analysis", "python-minimum-verified"}
    } == {"src/suitcode/mcp/service.py"}


def test_execution_task_file_contains_stable_fixture_execution_tasks() -> None:
    task_file = Path("benchmarks/codex/tasks/suitcode_execution.json")
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    assert len(tasks) == 2
    assert {task.task_id for task in tasks} == {"python-test-execution", "npm-build-execution"}
    assert {task.repository_path for task in tasks} == {"tests/test_repos/python", "tests/test_repos/npm"}
    assert {task.timeout_seconds for task in tasks} == {300}
    assert next(task for task in tasks if task.task_id == "python-test-execution").target_selector == {
        "test_id": "test:python:pytest:root"
    }
    assert next(task for task in tasks if task.task_id == "npm-build-execution").target_selector == {
        "action_id": "action:npm:build:@monorepo/codegen"
    }
