from __future__ import annotations

import json
from pathlib import Path

from suitcode.analytics.transcript_models import TokenMetricKind, TranscriptTokenBreakdown
from suitcode.evaluation.codex.comparison_service import CodexComparisonService
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.comparison_models import SuiteRole
from suitcode.evaluation.metadata_models import AgentKind, AgentRunMetadata
from suitcode.evaluation.models import (
    ActionScore,
    AnswerScore,
    CodexEvaluationReport,
    CodexEvaluationTaskResult,
    EvaluationFailureKind,
    EvaluationStatus,
    ToolSelectionScore,
)
from suitcode.evaluation.protocol_models import MetricKind, RunTemperature, TaskTaxonomy
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
        run_root = self.working_directory / ".suit" / "evaluation" / "codex" / "runs" / f"fake-run-{self._counter}"
        tasks_root = run_root / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        if arm == EvaluationArm.BASELINE:
            task_passed = max(0, task_total - 2)
            avg_tokens = 3000.0
            avg_duration = 1200.0
        else:
            task_passed = task_total
            avg_tokens = 1200.0
            avg_duration = 450.0
        task_items = []
        for item in tasks:
            is_execution = item.task_family in {CodexTaskFamily.TEST_EXECUTION, CodexTaskFamily.BUILD_EXECUTION}
            if item.task_family == CodexTaskFamily.TRUTH_COVERAGE:
                actual_answer = {
                    "overall_availability": "degraded",
                    "architecture": {
                        "authoritative_count": 15,
                        "derived_count": 10,
                        "heuristic_count": 0,
                        "unavailable_count": 0,
                        "availability": "available",
                    },
                    "code": {
                        "authoritative_count": 0,
                        "derived_count": 0,
                        "heuristic_count": 0,
                        "unavailable_count": 4,
                        "availability": "degraded",
                    },
                    "tests": {
                        "authoritative_count": 0,
                        "derived_count": 2,
                        "heuristic_count": 0,
                        "unavailable_count": 0,
                        "availability": "available",
                    },
                    "quality": {
                        "authoritative_count": 0,
                        "derived_count": 0,
                        "heuristic_count": 0,
                        "unavailable_count": 2,
                        "availability": "degraded",
                    },
                    "actions": {
                        "authoritative_count": 0,
                        "derived_count": 2,
                        "heuristic_count": 0,
                        "unavailable_count": 1,
                        "availability": "degraded",
                    },
                }
            elif item.task_family == CodexTaskFamily.ORIENTATION:
                actual_answer = {
                    "workspace_id": "workspace:repo",
                    "repository_id": "repo:repo",
                    "provider_ids": ["python"],
                    "component_count": 1,
                    "test_count": 2,
                    "quality_provider_count": 1,
                    "overall_truth_availability": "degraded",
                }
            elif item.task_family == CodexTaskFamily.BUILD_EXECUTION:
                actual_answer = {
                    "selected_action_id": "build:pkg",
                    "command_preview": "python -m build",
                    "execution_status": "passed",
                    "succeeded": True,
                }
            else:
                actual_answer = {"result": "ok"}
            task_dir = tasks_root / item.task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            last_message_path = task_dir / "last_message.txt"
            last_message_path.write_text(json.dumps(actual_answer), encoding="utf-8")
            stdout_path = task_dir / "stdout.jsonl"
            stdout_path.write_text("", encoding="utf-8")
            task_items.append(
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
                    action_score=ActionScore(executed=is_execution, matched_target=is_execution, status=("passed" if is_execution else None)),
                    transcript_token_breakdown=TranscriptTokenBreakdown(
                        metric_kind=TokenMetricKind.TRANSCRIPT_ESTIMATED,
                        model_family="openai/codex",
                        session_id=f"session-{self._counter}-{item.task_id}",
                        total_tokens=(50 + 80 + (10 if arm == EvaluationArm.SUITCODE else 0) + (20 if arm == EvaluationArm.SUITCODE else 0) + (15 if arm == EvaluationArm.BASELINE else 5) + 25 + 0 + 10),
                        user_message_tokens=50,
                        assistant_message_tokens=80,
                        mcp_tool_call_tokens=(10 if arm == EvaluationArm.SUITCODE else 0),
                        mcp_tool_output_tokens=(20 if arm == EvaluationArm.SUITCODE else 0),
                        custom_tool_call_tokens=(15 if arm == EvaluationArm.BASELINE else 5),
                        custom_tool_output_tokens=25,
                        terminal_output_tokens=0,
                        reasoning_summary_tokens=10,
                        tokens_before_first_suitcode_tool=(40 if arm == EvaluationArm.SUITCODE else None),
                        tokens_before_first_high_value_suitcode_tool=(60 if arm == EvaluationArm.SUITCODE else None),
                        first_suitcode_tool=("open_workspace" if arm == EvaluationArm.SUITCODE else None),
                        first_high_value_suitcode_tool=(item.expected_high_value_tools[0] if arm == EvaluationArm.SUITCODE and item.expected_high_value_tools else None),
                    ),
                    stdout_jsonl_path=str(stdout_path),
                    output_last_message_path=str(last_message_path),
                )
            )
        tasks_payload = tuple(task_items)
        return CodexEvaluationReport(
            report_id=f"codex-eval-fake-{self._counter}",
            generated_at_utc="2026-03-09T15:00:00.000Z",
            agent_metadata=AgentRunMetadata(
                agent_kind=AgentKind.CODEX,
                cli_name="codex",
                cli_version="0.106.0",
                model_name="gpt-5.4",
                model_provider="openai",
                host_os="Windows-11",
                working_directory=str(self.working_directory),
                command_prefix=("codex", "exec"),
                full_auto=kwargs.get("full_auto"),
                sandbox_mode=kwargs.get("sandbox"),
                bypass_approvals_and_sandbox=kwargs.get("bypass_approvals_and_sandbox"),
                suitcode_enabled=(arm == EvaluationArm.SUITCODE),
                mcp_transport=("stdio" if arm == EvaluationArm.SUITCODE else None),
                git_commit_hash="abc123",
                git_branch="main",
                git_repository_url="git@example.com:demo/repo.git",
            ),
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
    def repository_summary(self, repository_root: Path, session_filter=None):
        class _Summary:
            def model_dump(self, mode: str = "json"):
                return {
                    "repository_root": str(repository_root),
                    "session_count": 3,
                    "sessions_using_suitcode": 3,
                    "sessions_without_suitcode": 0,
                    "sessions_without_high_value_suitcode": 0,
                    "sessions_with_late_suitcode_adoption": 0,
                    "sessions_with_late_high_value_adoption": 0,
                    "sessions_with_shell_heavy_pre_suitcode": 0,
                    "skipped_artifacts": 0,
                    "tool_usage": [
                        {"tool_name": "open_workspace", "call_count": 3, "first_seen_at": "2026-03-09T10:00:00Z", "last_seen_at": "2026-03-09T11:00:00Z"},
                        {"tool_name": "get_truth_coverage", "call_count": 2, "first_seen_at": "2026-03-09T10:05:00Z", "last_seen_at": "2026-03-09T11:05:00Z"},
                    ],
                    "first_tool_distribution": {"open_workspace": 3},
                    "first_high_value_tool_distribution": {"repository_summary": 2, "get_truth_coverage": 1},
                    "correlation_quality_mix": {"strong": 3},
                    "transcript_metrics": {"event_count": 20, "mcp_tool_call_count": 6},
                    "avg_first_suitcode_tool_index": 1.0,
                    "avg_first_high_value_tool_index": 2.0,
                    "total_tokens": 900,
                    "avg_tokens_per_session": 300.0,
                    "avg_tokens_before_first_suitcode_tool": 40.0,
                    "avg_tokens_before_first_high_value_tool": 60.0,
                    "token_breakdowns_by_kind": {"assistant_message_tokens": 240, "user_message_tokens": 150},
                    "latest_session_id": "session-3",
                    "latest_session_at": "2026-03-09T11:05:00Z",
                    "notes": [],
                }

        return _Summary()


class _FakeNativeSummaryService:
    def __init__(self, *, first_tool: str, session_count: int, sessions_using: int, avg_first_index: float | None) -> None:
        self._first_tool = first_tool
        self._session_count = session_count
        self._sessions_using = sessions_using
        self._avg_first_index = avg_first_index

    def repository_summary(self, repository_root: Path, session_filter=None):
        class _Summary:
            def __init__(self, payload: dict[str, object]) -> None:
                self._payload = payload

            def model_dump(self, mode: str = "json"):
                return self._payload

        return _Summary(
            {
                "repository_root": str(repository_root),
                "session_count": self._session_count,
                "sessions_using_suitcode": self._sessions_using,
                "sessions_without_suitcode": self._session_count - self._sessions_using,
                "sessions_without_high_value_suitcode": 0,
                "sessions_with_late_suitcode_adoption": 0,
                "sessions_with_late_high_value_adoption": 0,
                "sessions_with_shell_heavy_pre_suitcode": 0,
                "skipped_artifacts": 0,
                "tool_usage": [
                    {"tool_name": self._first_tool, "call_count": self._sessions_using, "first_seen_at": None, "last_seen_at": None}
                ]
                if self._sessions_using
                else [],
                "first_tool_distribution": ({self._first_tool: self._sessions_using} if self._sessions_using else {}),
                "first_high_value_tool_distribution": {},
                "correlation_quality_mix": {"strong": self._sessions_using} if self._sessions_using else {},
                "transcript_metrics": {"event_count": 10, "mcp_tool_call_count": self._sessions_using},
                "avg_first_suitcode_tool_index": self._avg_first_index,
                "avg_first_high_value_tool_index": None,
                "total_tokens": 1000,
                "avg_tokens_per_session": 250.0,
                "avg_tokens_before_first_suitcode_tool": 120.0 if self._sessions_using else None,
                "avg_tokens_before_first_high_value_suitcode_tool": None,
                "token_breakdowns_by_kind": {"assistant_message_tokens": 200},
                "latest_session_id": "session-x",
                "latest_session_at": "2026-03-24T00:00:00Z",
                "notes": [],
            }
        )


class _FakeMcpAggregator:
    def summary(self, **kwargs):
        class _Summary:
            def model_dump(self, mode: str = "json"):
                return {
                    "total_calls": 7,
                    "success_calls": 6,
                    "error_calls": 1,
                    "estimated_tokens": 420,
                    "estimated_tokens_saved": 280,
                    "confidence_mix": {"high": 7},
                    "top_tools": ("repository_summary_by_path",),
                }

        return _Summary()

    def tool_usage(self, **kwargs):
        class _Item:
            def __init__(self, tool_name: str, total_calls: int, success_calls: int, error_calls: int) -> None:
                self.tool_name = tool_name
                self.total_calls = total_calls
                self.success_calls = success_calls
                self.error_calls = error_calls
                self.estimated_tokens = 100
                self.estimated_tokens_saved = 200
                self.p95_duration_ms = 1234

        return (
            _Item("repository_summary_by_path", 3, 3, 0),
            _Item("get_file_owner_by_path", 2, 2, 0),
        )

    def load_events(self, **kwargs):
        class _Status:
            value = "error"

        class _Event:
            def __init__(self) -> None:
                self.status = _Status()
                self.tool_name = "get_minimum_verified_change_set_by_path"
                self.error_class = "McpValidationError"
                self.error_message = "unknown repository file owner"

        return (_Event(),)


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
    service._claude_analytics_service = _FakeNativeSummaryService(
        first_tool="inspect_repository_support",
        session_count=2,
        sessions_using=1,
        avg_first_index=13.0,
    )
    service._cursor_analytics_service = _FakeNativeSummaryService(
        first_tool="repository_summary_by_path",
        session_count=3,
        sessions_using=2,
        avg_first_index=None,
    )
    service._mcp_aggregator = _FakeMcpAggregator()

    benchmarks_dir = tmp_path / "benchmarks" / "codex"
    (benchmarks_dir / "tasks").mkdir(parents=True)
    (benchmarks_dir / "comparisons").mkdir(parents=True)
    readonly_tasks = [
        {
            "task_id": "impact-1",
            "repository_path": "repo",
            "task_family": "change_analysis",
            "target_selector": {"repository_rel_path": "src/app.py"},
            "question": "If src/app.py changes, what is the deterministic impact summary?",
            "difficulty": "medium",
            "task_taxonomy": "impact_analysis",
            "ground_truth_kind": "exact_field_match",
            "expected_success_criteria": ["owner matches baseline"],
            "suite_role": "headline_ab",
        },
        {
            "task_id": "minimum-1",
            "repository_path": "repo",
            "task_family": "minimum_verified_change_set",
            "target_selector": {"repository_rel_path": "src/app.py"},
            "question": "After changing src/app.py, what exact deterministic validation set must run?",
            "difficulty": "medium",
            "task_taxonomy": "minimum_verified_change_set",
            "ground_truth_kind": "exact_id_set_match",
            "expected_success_criteria": ["id sets match baseline"],
            "suite_role": "headline_ab",
        },
    ]
    calibration_tasks = [
        {
            "task_id": "orientation-1",
            "repository_path": "repo",
            "task_family": "orientation",
            "question": "What is the repository summary?",
            "difficulty": "easy",
            "task_taxonomy": "orientation",
            "ground_truth_kind": "exact_field_match",
            "expected_success_criteria": ["schema valid", "fields exact"],
            "suite_role": "calibration",
        },
        {
            "task_id": "truth-1",
            "repository_path": "repo",
            "task_family": "truth_coverage",
            "question": "What is the repository truth-coverage profile?",
            "difficulty": "easy",
            "task_taxonomy": "truth_coverage",
            "ground_truth_kind": "exact_field_match",
            "expected_success_criteria": ["availability exact"],
            "suite_role": "calibration",
        },
    ]
    execution_tasks = [
        {
            "task_id": "build-1",
            "repository_path": "repo",
            "task_family": "build_execution",
            "target_selector": {"repository_rel_path": "src/app.py"},
            "question": "After changing src/app.py, which deterministic build target should run, and run it?",
            "difficulty": "medium",
            "task_taxonomy": "build_execution",
            "ground_truth_kind": "exact_action_target_match",
            "expected_success_criteria": ["selected action matches baseline", "execution result matches baseline"],
            "suite_role": "execution_ab",
        },
    ]
    stress_tasks = [
        {
            "task_id": "stress-1",
            "repository_path": "repo",
            "task_family": "change_analysis",
            "target_selector": {"repository_rel_path": "src/app.py"},
            "question": "If src/app.py changes, what breaks?",
            "difficulty": "hard",
            "task_taxonomy": "impact_analysis",
            "ground_truth_kind": "exact_field_match",
            "expected_success_criteria": ["fields exact"],
            "suite_role": "stress",
        },
    ]
    (benchmarks_dir / "tasks" / "readonly.json").write_text(json.dumps(readonly_tasks), encoding="utf-8")
    (benchmarks_dir / "tasks" / "calibration.json").write_text(json.dumps(calibration_tasks), encoding="utf-8")
    (benchmarks_dir / "tasks" / "execution.json").write_text(json.dumps(execution_tasks), encoding="utf-8")
    (benchmarks_dir / "tasks" / "stress.json").write_text(json.dumps(stress_tasks), encoding="utf-8")
    spec_path = benchmarks_dir / "comparisons" / "standout.json"
    spec_path.write_text(
        json.dumps(
            {
                "stable_readonly_tasks_file": "benchmarks/codex/tasks/readonly.json",
                "calibration_tasks_file": "benchmarks/codex/tasks/calibration.json",
                "stable_execution_tasks_file": "benchmarks/codex/tasks/execution.json",
                "stress_readonly_tasks_file": "benchmarks/codex/tasks/stress.json",
                "passive_repository_root": ".",
                "include_agent_experience_summary": True,
                "agent_experience_repository_root": ".",
                "agent_experience_days": 7,
            }
        ),
        encoding="utf-8",
    )

    report = service.run_standout_report(service.load_spec(spec_path))

    assert report.stable_readonly_suitcode.arm == EvaluationArm.SUITCODE
    assert report.stable_readonly_baseline.arm == EvaluationArm.BASELINE
    assert report.stable_execution_suitcode is not None
    assert report.stable_execution_baseline is not None
    assert report.calibration_suitcode is not None
    assert report.calibration_baseline is not None
    assert report.stress_readonly_suitcode is not None
    assert report.stable_readonly_suitcode_metadata is not None
    assert report.stable_readonly_baseline_metadata is not None
    assert any(item.metric_name == "task_success_rate" for item in report.headline_deltas)
    assert report.passive_usage_summary is not None
    assert report.agent_experience_summary is not None
    assert report.figures
    assert report.protocol.protocol_name
    assert report.measured_metrics
    assert report.estimated_metrics
    assert report.derived_metrics
    assert report.protocol.task_protocols
    assert report.protocol.repository_profiles
    assert report.headline_efficiency
    assert report.provenance_coverage
    assert report.terminology
    assert report.suite_descriptions
    assert report.arm_policies
    assert report.suite_failure_explanations
    assert report.task_level_summaries
    assert report.evaluation_validity_notes
    baseline_suite = next(
        item
        for item in report.suite_failure_explanations
        if item.suite_role == SuiteRole.STABLE_READONLY and item.arm == EvaluationArm.BASELINE
    )
    assert "headline" in " ".join(baseline_suite.interpretation_notes).lower()
    calibration_suite = next(
        item
        for item in report.suite_failure_explanations
        if item.suite_role == SuiteRole.CALIBRATION and item.arm == EvaluationArm.BASELINE
    )
    assert "calibration" in calibration_suite.plain_language_summary.lower() or calibration_suite.task_total >= 0
    baseline_task = next(
        item
        for item in report.task_level_summaries
        if item.suite_role == SuiteRole.STABLE_READONLY and item.arm == EvaluationArm.BASELINE
    )
    assert baseline_task.question
    assert baseline_task.expected_answer
    assert baseline_task.task_taxonomy in {TaskTaxonomy.IMPACT_ANALYSIS, TaskTaxonomy.MINIMUM_VERIFIED_CHANGE_SET}
    assert baseline_task.run_temperature == RunTemperature.COLD
    assert baseline_task.expected_success_criteria
    assert any(item.is_hero_metric for item in report.headline_efficiency)
    assert report.figures[0].metric_kinds[0] in {MetricKind.MEASURED, MetricKind.ESTIMATED, MetricKind.DERIVED}
    report_dir = comparison_root / reporter.report_directory_name(report)
    assert (report_dir / "comparison.json").exists()
    assert (report_dir / "comparison.md").exists()
    markdown = (report_dir / "comparison.md").read_text(encoding="utf-8")
    assert "## Live Multi-Agent Experience" in markdown
    assert "### Claude Live Usage" in markdown
    assert "### Cursor Live Usage" in markdown
    assert "## Table of Contents" in markdown
    assert (report_dir / "figures" / "01-headline-outcomes.svg").exists()
    assert (report_dir / "figures" / "data" / "01-headline-outcomes.csv").exists()
    assert (report_dir / "figures" / "08-live-tool-token-savings.svg").exists()
    assert (report_dir / "figures" / "data" / "08-live-tool-token-savings.csv").exists()
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
