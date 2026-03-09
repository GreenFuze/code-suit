from __future__ import annotations

import json
from pathlib import Path

from suitcode.evaluation.codex.comparison_service import CodexComparisonService
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.models import (
    ActionScore,
    AnswerScore,
    CodexEvaluationReport,
    CodexEvaluationTaskResult,
    EvaluationFailureKind,
    EvaluationStatus,
    ToolSelectionScore,
)
from suitcode.evaluation.reporting import CodexComparisonReporter


class _FakeEvaluationService:
    def __init__(self, working_directory: Path) -> None:
        self.working_directory = working_directory
        self.calls: list[dict[str, object]] = []
        self._counter = 0

    def load_tasks(self, tasks_file: Path):
        payload = json.loads(tasks_file.read_text(encoding="utf-8"))
        return tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    def run(self, tasks, **kwargs):
        self.calls.append({"tasks": tasks, **kwargs})
        self._counter += 1
        arm = kwargs.get("prompt_arm", EvaluationArm.SUITCODE)
        task_total = len(tasks)
        if arm == EvaluationArm.BASELINE:
            task_passed = max(0, task_total - 2)
            avg_tokens = 3000.0
            avg_duration = 1200.0
        else:
            task_passed = task_total
            avg_tokens = 1200.0
            avg_duration = 450.0
        tasks_payload = tuple(
            CodexEvaluationTaskResult(
                task_id=item.task_id,
                task_family=item.task_family.value,
                status=EvaluationStatus.PASSED,
                repository_root=str(self.working_directory / item.repository_path),
                duration_ms=100,
                required_tool_count=len(item.expected_required_tools),
                used_suitcode_tool_count=len(item.expected_required_tools) if arm == EvaluationArm.SUITCODE else 0,
                used_high_value_tool_count=len(item.expected_high_value_tools) if arm == EvaluationArm.SUITCODE else 0,
                first_suitcode_tool_index=(1 if arm == EvaluationArm.SUITCODE else None),
                first_high_value_tool_index=(2 if arm == EvaluationArm.SUITCODE and item.expected_high_value_tools else None),
                tool_selection=ToolSelectionScore(
                    required_tools_present=True,
                    required_tool_names=item.expected_required_tools,
                    used_tool_names=item.expected_required_tools if arm == EvaluationArm.SUITCODE else tuple(),
                    first_suitcode_tool=("open_workspace" if arm == EvaluationArm.SUITCODE else None),
                    first_high_value_tool=(item.expected_high_value_tools[0] if arm == EvaluationArm.SUITCODE and item.expected_high_value_tools else None),
                    first_high_value_tool_index=(2 if arm == EvaluationArm.SUITCODE and item.expected_high_value_tools else None),
                    used_high_value_tool_early=(arm == EvaluationArm.SUITCODE and bool(item.expected_high_value_tools)),
                ),
                answer_score=AnswerScore(schema_valid=True),
                action_score=ActionScore(executed=False, matched_target=False),
                stdout_jsonl_path="stdout.jsonl",
                output_last_message_path="last_message.txt",
            )
            for item in tasks
        )
        return CodexEvaluationReport(
            report_id=f"codex-eval-fake-{self._counter}",
            generated_at_utc="2026-03-09T15:00:00.000Z",
            task_total=task_total,
            task_passed=task_passed,
            task_failed=task_total - task_passed,
            task_error=0,
            avg_duration_ms=avg_duration,
            avg_transcript_tokens=avg_tokens,
            avg_tokens_before_first_suitcode_tool=(200.0 if arm == EvaluationArm.SUITCODE else None),
            avg_tokens_before_first_high_value_tool=(350.0 if arm == EvaluationArm.SUITCODE else None),
            required_tool_success_rate=1.0 if arm == EvaluationArm.SUITCODE else 0.5,
            high_value_tool_early_rate=1.0 if arm == EvaluationArm.SUITCODE else 0.0,
            answer_schema_success_rate=1.0,
            deterministic_action_success_rate=1.0 if all(item.task_family in {CodexTaskFamily.TEST_EXECUTION, CodexTaskFamily.BUILD_EXECUTION} for item in tasks) else 0.0,
            correlation_quality_mix={"strong": task_total} if arm == EvaluationArm.SUITCODE else {},
            tasks=tasks_payload,
        )


class _FakeAnalyticsService:
    def repository_summary(self, repository_root: Path):
        class _Summary:
            def model_dump(self, mode: str = "json"):
                return {
                    "repository_root": str(repository_root),
                    "session_count": 3,
                    "sessions_using_suitcode": 3,
                    "sessions_without_suitcode": 0,
                }

        return _Summary()


def test_comparison_service_runs_arms_and_writes_report(tmp_path: Path) -> None:
    comparison_root = tmp_path / ".suit" / "evaluation" / "codex" / "comparisons"
    reporter = CodexComparisonReporter(comparison_root)
    eval_service = _FakeEvaluationService(tmp_path)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        "[mcp_servers.suitcode]\ncommand = \"cmd\"\nargs = [\"/c\", \"run_mcp.bat\"]\n",
        encoding="utf-8",
    )
    service = CodexComparisonService(
        working_directory=tmp_path,
        evaluation_service=eval_service,
        comparison_reporter=reporter,
        analytics_service=_FakeAnalyticsService(),
    )

    benchmarks_dir = tmp_path / "benchmarks" / "codex"
    (benchmarks_dir / "tasks").mkdir(parents=True)
    (benchmarks_dir / "comparisons").mkdir(parents=True)
    readonly_tasks = [
        {"task_id": "orientation-1", "repository_path": "repo", "task_family": "orientation"},
        {"task_id": "truth-1", "repository_path": "repo", "task_family": "truth_coverage"},
    ]
    execution_tasks = [
        {"task_id": "build-1", "repository_path": "repo", "task_family": "build_execution", "target_selector": {"action_id": "build:pkg"}},
    ]
    stress_tasks = [
        {"task_id": "stress-1", "repository_path": "repo", "task_family": "change_analysis", "target_selector": {"repository_rel_path": "src/app.py"}},
    ]
    (benchmarks_dir / "tasks" / "readonly.json").write_text(json.dumps(readonly_tasks), encoding="utf-8")
    (benchmarks_dir / "tasks" / "execution.json").write_text(json.dumps(execution_tasks), encoding="utf-8")
    (benchmarks_dir / "tasks" / "stress.json").write_text(json.dumps(stress_tasks), encoding="utf-8")
    spec_path = benchmarks_dir / "comparisons" / "standout.json"
    spec_path.write_text(
        json.dumps(
            {
                "stable_readonly_tasks_file": "benchmarks/codex/tasks/readonly.json",
                "stable_execution_tasks_file": "benchmarks/codex/tasks/execution.json",
                "stress_readonly_tasks_file": "benchmarks/codex/tasks/stress.json",
                "passive_repository_root": ".",
            }
        ),
        encoding="utf-8",
    )

    report = service.run_standout_report(service.load_spec(spec_path))

    assert report.stable_readonly_suitcode.arm == EvaluationArm.SUITCODE
    assert report.stable_readonly_baseline.arm == EvaluationArm.BASELINE
    assert report.stable_execution_suitcode is not None
    assert report.stress_readonly_suitcode is not None
    assert any(item.metric_name == "task_success_rate" for item in report.headline_deltas)
    assert report.passive_usage_summary is not None
    assert (comparison_root / report.report_id / "comparison.json").exists()
    assert (comparison_root / report.report_id / "comparison.md").exists()
    baseline_call = next(call for call in eval_service.calls if call["prompt_arm"] == EvaluationArm.BASELINE)
    assert len(baseline_call["config_overrides"]) == 1
    assert "mcp_servers.suitcode={" in baseline_call["config_overrides"][0]
    assert "enabled=false" in baseline_call["config_overrides"][0]


def test_comparison_service_rejects_usage_limit_reports(tmp_path: Path) -> None:
    comparison_root = tmp_path / ".suit" / "evaluation" / "codex" / "comparisons"
    reporter = CodexComparisonReporter(comparison_root)
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_text(
        "[mcp_servers.suitcode]\ncommand = \"cmd\"\nargs = [\"/c\", \"run_mcp.bat\"]\n",
        encoding="utf-8",
    )

    class _UsageLimitEvaluationService(_FakeEvaluationService):
        def run(self, tasks, **kwargs):
            report = super().run(tasks, **kwargs)
            if kwargs.get("prompt_arm") == EvaluationArm.BASELINE:
                task = report.tasks[0].model_copy(
                    update={
                        "status": EvaluationStatus.ERROR,
                        "failure_kind": EvaluationFailureKind.USAGE_LIMIT,
                        "failure_summary": "Codex usage limit reached before task completion",
                    }
                )
                return report.model_copy(
                    update={
                        "task_passed": 0,
                        "task_failed": 0,
                        "task_error": report.task_total,
                        "failure_kind_mix": {EvaluationFailureKind.USAGE_LIMIT.value: report.task_total},
                        "infrastructure_failure_kind_mix": {EvaluationFailureKind.USAGE_LIMIT.value: report.task_total},
                        "tasks": tuple(task if index == 0 else item for index, item in enumerate(report.tasks)),
                    }
                )
            return report

    service = CodexComparisonService(
        working_directory=tmp_path,
        evaluation_service=_UsageLimitEvaluationService(tmp_path),
        comparison_reporter=reporter,
        analytics_service=_FakeAnalyticsService(),
    )

    benchmarks_dir = tmp_path / "benchmarks" / "codex"
    (benchmarks_dir / "tasks").mkdir(parents=True)
    (benchmarks_dir / "comparisons").mkdir(parents=True)
    (benchmarks_dir / "tasks" / "readonly.json").write_text(
        json.dumps([{"task_id": "truth-1", "repository_path": "repo", "task_family": "truth_coverage"}]),
        encoding="utf-8",
    )
    (benchmarks_dir / "tasks" / "execution.json").write_text(
        json.dumps([{"task_id": "build-1", "repository_path": "repo", "task_family": "build_execution", "target_selector": {"action_id": "build:pkg"}}]),
        encoding="utf-8",
    )
    (benchmarks_dir / "tasks" / "stress.json").write_text(
        json.dumps([{"task_id": "stress-1", "repository_path": "repo", "task_family": "change_analysis", "target_selector": {"repository_rel_path": "src/app.py"}}]),
        encoding="utf-8",
    )
    spec_path = benchmarks_dir / "comparisons" / "standout.json"
    spec_path.write_text(
        json.dumps(
            {
                "stable_readonly_tasks_file": "benchmarks/codex/tasks/readonly.json",
                "stable_execution_tasks_file": "benchmarks/codex/tasks/execution.json",
                "stress_readonly_tasks_file": "benchmarks/codex/tasks/stress.json",
                "passive_repository_root": ".",
            }
        ),
        encoding="utf-8",
    )

    try:
        service.run_standout_report(service.load_spec(spec_path))
    except RuntimeError as exc:
        assert "usage limit" in str(exc).lower()
    else:
        raise AssertionError("expected usage limit reports to invalidate the comparison")
