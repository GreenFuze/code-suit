from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from statistics import median
import tomllib
from uuid import uuid4
from typing import Any

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.analytics.claude_analytics_service import ClaudeAnalyticsService
from suitcode.analytics.claude_session_store import ClaudeSessionStore
from suitcode.analytics.claude_transcript_capture import ClaudeTranscriptCaptureBuilder
from suitcode.analytics.codex_analytics_service import CodexAnalyticsService
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.cursor_analytics_service import CursorAnalyticsService
from suitcode.analytics.cursor_session_store import CursorSessionStore
from suitcode.analytics.cursor_transcript_capture import CursorTranscriptCaptureBuilder
from suitcode.analytics.live_usage_filters import event_matches_live_filters, session_matches_live_filters
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.evaluation.metadata_models import AgentKind
from suitcode.core.action_models import ActionKind
from suitcode.core.workspace import Workspace
from suitcode.evaluation.codex.figure_generation import CodexComparisonFigureBuilder
from suitcode.evaluation.codex.service import CodexEvaluationService
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.comparison_models import (
    ArmPolicyDescription,
    ArmRunReference,
    CodexStandoutComparisonSpec,
    CodexStandoutReport,
    ComparisonDelta,
    EvaluationArm,
    HeadlineEfficiencyMetric,
    ProvenanceCoverageSummary,
    SuiteDescription,
    SuiteFailureExplanation,
    SuiteRole,
    TaskFailureExplanation,
    TerminologyEntry,
)
from suitcode.evaluation.models import CodexEvaluationReport, CodexEvaluationTaskResult, EvaluationFailureKind, EvaluationStatus
from suitcode.evaluation.protocol_models import (
    BenchmarkCondition,
    BenchmarkProtocol,
    GroundTruthKind,
    MetricDefinition,
    MetricKind,
    RepositoryProfile,
    RunTemperature,
    TaskProtocol,
    TaskTaxonomy,
)
from suitcode.evaluation.reporting import CodexComparisonReporter
from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS


class CodexComparisonService:
    def __init__(
        self,
        *,
        working_directory: Path | None = None,
        evaluation_service: CodexEvaluationService | None = None,
        comparison_reporter: CodexComparisonReporter | None = None,
        analytics_service: CodexAnalyticsService | None = None,
    ) -> None:
        self._working_directory = (working_directory or Path.cwd()).expanduser().resolve()
        self._evaluation_service = evaluation_service or CodexEvaluationService(working_directory=self._working_directory)
        self._comparison_reporter = comparison_reporter or CodexComparisonReporter(
            self._working_directory / ".suit" / "evaluation" / "codex" / "comparisons"
        )
        settings = AnalyticsSettings.from_env()
        analytics_store = JsonlAnalyticsStore(settings)
        correlation = AnalyticsCorrelationService(analytics_store)
        token_estimator = TranscriptTokenEstimator()
        if analytics_service is None:
            analytics_service = CodexAnalyticsService(
                CodexSessionStore(),
                correlation_service=correlation,
                capture_builder=CodexTranscriptCaptureBuilder(),
                token_estimator=token_estimator,
            )
        self._analytics_service = analytics_service
        self._claude_analytics_service = ClaudeAnalyticsService(
            ClaudeSessionStore(),
            correlation_service=correlation,
            capture_builder=ClaudeTranscriptCaptureBuilder(),
            token_estimator=token_estimator,
        )
        cursor_store = CursorSessionStore()
        self._cursor_analytics_service = CursorAnalyticsService(
            cursor_store,
            correlation_service=correlation,
            capture_builder=CursorTranscriptCaptureBuilder(cursor_store),
            token_estimator=token_estimator,
        )
        self._mcp_aggregator = AnalyticsAggregator(
            analytics_store,
            tool_catalog=tuple(sorted(TOOL_DESCRIPTIONS)),
            excluded_tools=(
                "get_analytics_summary",
                "get_tool_usage_analytics",
                "get_inefficient_tool_calls",
                "get_mcp_benchmark_report",
            ),
        )

    def load_spec(self, spec_path: Path) -> CodexStandoutComparisonSpec:
        resolved = spec_path.expanduser().resolve()
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return CodexStandoutComparisonSpec.model_validate(payload)

    def run_standout_report(
        self,
        spec: CodexStandoutComparisonSpec,
        *,
        model: str | None = None,
        profile_suitcode: str | None = None,
        profile_baseline: str | None = None,
        stable_timeout_seconds: int | None = None,
        stress_timeout_seconds: int | None = None,
        skip_stress: bool = False,
        skip_execution: bool = False,
    ) -> CodexStandoutReport:
        comparison_id = f"codex-comparison-{uuid4().hex}"
        readonly_full_auto = False
        readonly_sandbox = "danger-full-access"
        readonly_bypass = True

        stable_readonly_tasks = self._load_tasks(spec.stable_readonly_tasks_file, timeout_seconds=stable_timeout_seconds or spec.stable_timeout_seconds)
        stable_readonly_suitcode = self._evaluation_service.run(
            stable_readonly_tasks,
            model=model,
            profile=profile_suitcode,
            prompt_arm=EvaluationArm.SUITCODE,
            full_auto=readonly_full_auto,
            sandbox=readonly_sandbox,
            bypass_approvals_and_sandbox=readonly_bypass,
        )
        self._ensure_report_usable(stable_readonly_suitcode, suite_label="stable read-only SuitCode arm")
        stable_readonly_baseline = self._evaluation_service.run(
            stable_readonly_tasks,
            model=model,
            profile=profile_baseline,
            prompt_arm=EvaluationArm.BASELINE,
            config_overrides=(self._baseline_disable_override(),),
            full_auto=readonly_full_auto,
            sandbox=readonly_sandbox,
            bypass_approvals_and_sandbox=readonly_bypass,
        )
        self._ensure_report_usable(stable_readonly_baseline, suite_label="stable read-only baseline arm")

        calibration_tasks: tuple[CodexEvaluationTask, ...] | None = None
        calibration_suitcode: CodexEvaluationReport | None = None
        calibration_baseline: CodexEvaluationReport | None = None
        if spec.calibration_tasks_file is not None:
            calibration_tasks = self._load_tasks(spec.calibration_tasks_file, timeout_seconds=stable_timeout_seconds or spec.stable_timeout_seconds)
            calibration_suitcode = self._evaluation_service.run(
                calibration_tasks,
                model=model,
                profile=profile_suitcode,
                prompt_arm=EvaluationArm.SUITCODE,
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )
            self._ensure_report_usable(calibration_suitcode, suite_label="calibration SuitCode arm")
            calibration_baseline = self._evaluation_service.run(
                calibration_tasks,
                model=model,
                profile=profile_baseline,
                prompt_arm=EvaluationArm.BASELINE,
                config_overrides=(self._baseline_disable_override(),),
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )
            self._ensure_report_usable(calibration_baseline, suite_label="calibration baseline arm")

        stable_execution_report: CodexEvaluationReport | None = None
        stable_execution_baseline: CodexEvaluationReport | None = None
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None = None
        if spec.include_stable_execution and not skip_execution:
            stable_execution_tasks = self._load_tasks(spec.stable_execution_tasks_file, timeout_seconds=stable_timeout_seconds or spec.stable_timeout_seconds)
            stable_execution_report = self._evaluation_service.run(
                stable_execution_tasks,
                model=model,
                profile=profile_suitcode,
                prompt_arm=EvaluationArm.SUITCODE,
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )
            self._ensure_report_usable(stable_execution_report, suite_label="stable execution SuitCode arm")
            stable_execution_baseline = self._evaluation_service.run(
                stable_execution_tasks,
                model=model,
                profile=profile_baseline,
                prompt_arm=EvaluationArm.BASELINE,
                config_overrides=(self._baseline_disable_override(),),
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )
            self._ensure_report_usable(stable_execution_baseline, suite_label="stable execution baseline arm")

        stress_report: CodexEvaluationReport | None = None
        stress_baseline: CodexEvaluationReport | None = None
        stress_tasks: tuple[CodexEvaluationTask, ...] | None = None
        if spec.include_stress_readonly and not skip_stress:
            stress_tasks = self._load_tasks(spec.stress_readonly_tasks_file, timeout_seconds=stress_timeout_seconds or spec.stress_timeout_seconds)
            stress_report = self._evaluation_service.run(
                stress_tasks,
                model=model,
                profile=profile_suitcode,
                prompt_arm=EvaluationArm.SUITCODE,
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )
            self._ensure_report_usable(stress_report, suite_label="stress read-only SuitCode arm")
            stress_baseline = self._evaluation_service.run(
                stress_tasks,
                model=model,
                profile=profile_baseline,
                prompt_arm=EvaluationArm.BASELINE,
                config_overrides=(self._baseline_disable_override(),),
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            )

        passive_summary = None
        if spec.include_passive_usage_summary:
            passive_root = (self._working_directory / spec.passive_repository_root).expanduser().resolve()
            passive_summary = self._analytics_service.repository_summary(passive_root).model_dump(mode="json")
        agent_experience_summary = None
        if spec.include_agent_experience_summary and spec.agent_experience_repository_root is not None:
            agent_root = (self._working_directory / spec.agent_experience_repository_root).expanduser().resolve()
            agent_experience_summary = self._agent_experience_summary(
                repository_root=agent_root,
                days=spec.agent_experience_days,
            )

        report = self._build_report(
            report_id=comparison_id,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            spec=spec,
            model=model,
            stable_readonly_tasks=stable_readonly_tasks,
            stable_readonly_suitcode=stable_readonly_suitcode,
            stable_readonly_baseline=stable_readonly_baseline,
            calibration_tasks=calibration_tasks,
            calibration_suitcode=calibration_suitcode,
            calibration_baseline=calibration_baseline,
            stable_execution_tasks=(stable_execution_tasks if stable_execution_report is not None else None),
            stable_execution_report=stable_execution_report,
            stable_execution_baseline=stable_execution_baseline,
            stress_tasks=(stress_tasks if stress_report is not None else None),
            stress_report=stress_report,
            stress_baseline=stress_baseline,
            passive_summary=passive_summary,
            agent_experience_summary=agent_experience_summary,
            stable_timeout_seconds=stable_timeout_seconds or spec.stable_timeout_seconds,
            stress_timeout_seconds=stress_timeout_seconds or spec.stress_timeout_seconds,
            full_auto=readonly_full_auto,
            sandbox=readonly_sandbox,
            bypass_approvals_and_sandbox=readonly_bypass,
            profile_suitcode=profile_suitcode,
            profile_baseline=profile_baseline,
            skip_execution=skip_execution,
            skip_stress=skip_stress,
        )
        run_dir = self._comparison_reporter.comparisons_root / self._comparison_reporter.report_directory_name(report)
        figures = CodexComparisonFigureBuilder().build(
            report=report,
            run_dir=run_dir,
            stable_readonly_suitcode_report=stable_readonly_suitcode,
            stable_readonly_baseline_report=stable_readonly_baseline,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline_report=stable_execution_baseline,
            stress_report=stress_report,
            stress_baseline_report=stress_baseline,
        )
        report = report.model_copy(update={"figures": figures})
        markdown = self._markdown_report(report)
        self._comparison_reporter.write_report(
            report,
            comparison_markdown=markdown,
            inputs={
                "spec": spec.model_dump(mode="json"),
                "stable_readonly_suitcode_report_id": stable_readonly_suitcode.report_id,
                "stable_readonly_baseline_report_id": stable_readonly_baseline.report_id,
                "calibration_suitcode_report_id": calibration_suitcode.report_id if calibration_suitcode is not None else None,
                "calibration_baseline_report_id": calibration_baseline.report_id if calibration_baseline is not None else None,
                "stable_execution_report_id": stable_execution_report.report_id if stable_execution_report is not None else None,
                "stable_execution_baseline_report_id": stable_execution_baseline.report_id if stable_execution_baseline is not None else None,
                "stress_report_id": stress_report.report_id if stress_report is not None else None,
                "stress_baseline_report_id": stress_baseline.report_id if stress_baseline is not None else None,
                "model": model,
                "profile_suitcode": profile_suitcode,
                "profile_baseline": profile_baseline,
                "skip_execution": skip_execution,
                "skip_stress": skip_stress,
                "stable_timeout_seconds": stable_timeout_seconds,
                "stress_timeout_seconds": stress_timeout_seconds,
            },
        )
        return report

    def load_report(self, report_id: str) -> CodexStandoutReport:
        return self._comparison_reporter.load_report(report_id)

    def load_latest_report(self) -> CodexStandoutReport | None:
        return self._comparison_reporter.load_latest_report()

    def refresh_report(self, report_id: str) -> CodexStandoutReport:
        run_dir = self._comparison_reporter.resolve_report_directory(report_id)
        inputs_path = run_dir / "inputs.json"
        report_path = run_dir / "comparison.json"
        if not inputs_path.exists():
            raise ValueError(f"Codex comparison inputs not found: `{inputs_path}`")
        if not report_path.exists():
            raise ValueError(f"Codex comparison report not found: `{report_path}`")
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        existing_report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        spec = CodexStandoutComparisonSpec.model_validate(inputs["spec"])
        stable_readonly_tasks = self._load_tasks(spec.stable_readonly_tasks_file, timeout_seconds=None)
        stable_readonly_suitcode = self._evaluation_service.load_report(inputs["stable_readonly_suitcode_report_id"])
        stable_readonly_baseline = self._evaluation_service.load_report(inputs["stable_readonly_baseline_report_id"])
        calibration_suitcode = self._evaluation_service.load_report(inputs["calibration_suitcode_report_id"]) if inputs.get("calibration_suitcode_report_id") else None
        calibration_baseline = self._evaluation_service.load_report(inputs["calibration_baseline_report_id"]) if inputs.get("calibration_baseline_report_id") else None
        calibration_tasks = self._load_tasks(spec.calibration_tasks_file, timeout_seconds=None) if spec.calibration_tasks_file and calibration_suitcode is not None else None
        stable_execution_report = (
            self._evaluation_service.load_report(inputs["stable_execution_report_id"])
            if inputs.get("stable_execution_report_id")
            else None
        )
        stable_execution_baseline = (
            self._evaluation_service.load_report(inputs["stable_execution_baseline_report_id"])
            if inputs.get("stable_execution_baseline_report_id")
            else None
        )
        stress_report = self._evaluation_service.load_report(inputs["stress_report_id"]) if inputs.get("stress_report_id") else None
        stress_baseline = self._evaluation_service.load_report(inputs["stress_baseline_report_id"]) if inputs.get("stress_baseline_report_id") else None
        stable_execution_tasks = self._load_tasks(spec.stable_execution_tasks_file, timeout_seconds=None) if stable_execution_report is not None else None
        stress_tasks = self._load_tasks(spec.stress_readonly_tasks_file, timeout_seconds=None) if stress_report is not None or stress_baseline is not None else None
        passive_summary = None
        if spec.include_passive_usage_summary:
            passive_root = (self._working_directory / spec.passive_repository_root).expanduser().resolve()
            passive_summary = self._analytics_service.repository_summary(passive_root).model_dump(mode="json")
        agent_experience_summary = None
        if spec.include_agent_experience_summary and spec.agent_experience_repository_root is not None:
            agent_root = (self._working_directory / spec.agent_experience_repository_root).expanduser().resolve()
            agent_experience_summary = self._agent_experience_summary(
                repository_root=agent_root,
                days=spec.agent_experience_days,
            )
        report = self._build_report(
            report_id=report_id,
            generated_at_utc=str(existing_report_payload.get("generated_at_utc", datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"))),
            spec=spec,
            model=inputs.get("model"),
            stable_readonly_tasks=stable_readonly_tasks,
            stable_readonly_suitcode=stable_readonly_suitcode,
            stable_readonly_baseline=stable_readonly_baseline,
            calibration_tasks=calibration_tasks,
            calibration_suitcode=calibration_suitcode,
            calibration_baseline=calibration_baseline,
            stable_execution_tasks=stable_execution_tasks,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline=stable_execution_baseline,
            stress_tasks=stress_tasks,
            stress_report=stress_report,
            stress_baseline=stress_baseline,
            passive_summary=passive_summary,
            agent_experience_summary=agent_experience_summary,
            stable_timeout_seconds=inputs.get("stable_timeout_seconds") or spec.stable_timeout_seconds,
            stress_timeout_seconds=inputs.get("stress_timeout_seconds") or spec.stress_timeout_seconds,
            full_auto=False,
            sandbox="danger-full-access",
            bypass_approvals_and_sandbox=True,
            profile_suitcode=inputs.get("profile_suitcode"),
            profile_baseline=inputs.get("profile_baseline"),
            skip_execution=bool(inputs.get("skip_execution", False)),
            skip_stress=bool(inputs.get("skip_stress", False)),
        )
        run_dir = self._comparison_reporter.comparisons_root / self._comparison_reporter.report_directory_name(report)
        figures = CodexComparisonFigureBuilder().build(
            report=report,
            run_dir=run_dir,
            stable_readonly_suitcode_report=stable_readonly_suitcode,
            stable_readonly_baseline_report=stable_readonly_baseline,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline_report=stable_execution_baseline,
            stress_report=stress_report,
            stress_baseline_report=stress_baseline,
        )
        report = report.model_copy(update={"figures": figures})
        self._comparison_reporter.write_report(report, comparison_markdown=self._markdown_report(report), inputs=inputs)
        return report

    def _build_report(
        self,
        *,
        report_id: str,
        generated_at_utc: str,
        spec: CodexStandoutComparisonSpec,
        model: str | None,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        stable_readonly_suitcode: CodexEvaluationReport,
        stable_readonly_baseline: CodexEvaluationReport,
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        calibration_suitcode: CodexEvaluationReport | None,
        calibration_baseline: CodexEvaluationReport | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_report: CodexEvaluationReport | None,
        stable_execution_baseline: CodexEvaluationReport | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
        passive_summary: dict[str, object] | None,
        agent_experience_summary: dict[str, object] | None,
        stable_timeout_seconds: int | None,
        stress_timeout_seconds: int | None,
        full_auto: bool,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
        profile_suitcode: str | None,
        profile_baseline: str | None,
        skip_execution: bool,
        skip_stress: bool,
    ) -> CodexStandoutReport:
        suite_descriptions = self._suite_descriptions(
            spec=spec,
            stable_readonly_tasks=stable_readonly_tasks,
            calibration_tasks=calibration_tasks,
            stable_execution_tasks=stable_execution_tasks,
            stress_tasks=stress_tasks,
        )
        arm_policies = self._arm_policies()
        suite_failure_explanations = self._suite_failure_explanations(
            stable_readonly_suitcode=stable_readonly_suitcode,
            stable_readonly_baseline=stable_readonly_baseline,
            calibration_suitcode=calibration_suitcode,
            calibration_baseline=calibration_baseline,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline=stable_execution_baseline,
            stress_report=stress_report,
            stress_baseline=stress_baseline,
            skip_stress=skip_stress,
        )
        task_level_summaries = self._task_level_summaries(
            stable_readonly_tasks=stable_readonly_tasks,
            stable_readonly_suitcode=stable_readonly_suitcode,
            stable_readonly_baseline=stable_readonly_baseline,
            calibration_tasks=calibration_tasks,
            calibration_suitcode=calibration_suitcode,
            calibration_baseline=calibration_baseline,
            stable_execution_tasks=stable_execution_tasks,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline=stable_execution_baseline,
            stress_tasks=stress_tasks,
            stress_report=stress_report,
            stress_baseline=stress_baseline,
        )
        evaluation_validity_notes = self._evaluation_validity_notes(
            stable_readonly_baseline=stable_readonly_baseline,
            calibration_baseline=calibration_baseline,
            stable_execution_report=stable_execution_report,
            stable_execution_baseline=stable_execution_baseline,
            stress_report=stress_report,
            stress_baseline=stress_baseline,
            skip_stress=skip_stress,
        )
        protocol = self._protocol(
            spec=spec,
            model=model,
            stable_readonly_tasks=stable_readonly_tasks,
            stable_readonly_suitcode=stable_readonly_suitcode,
            calibration_suitcode=calibration_suitcode,
            calibration_tasks=calibration_tasks,
            stable_execution_tasks=stable_execution_tasks,
            stable_execution_report=stable_execution_report,
            stress_tasks=stress_tasks,
            stress_report=stress_report,
            stress_baseline=stress_baseline,
            stable_timeout_seconds=stable_timeout_seconds,
            stress_timeout_seconds=stress_timeout_seconds,
            sandbox=sandbox,
            bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
        )
        metric_groups = self._metric_groups(protocol.metric_definitions)
        headline_efficiency = self._headline_efficiency(task_level_summaries)
        provenance_coverage = self._provenance_coverage(task_level_summaries=task_level_summaries)
        return CodexStandoutReport(
            report_id=report_id,
            generated_at_utc=generated_at_utc,
            model=model,
            stable_readonly_suitcode=self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STABLE_READONLY, stable_readonly_suitcode),
            stable_readonly_baseline=self._arm_run_reference(EvaluationArm.BASELINE, SuiteRole.STABLE_READONLY, stable_readonly_baseline),
            stable_readonly_suitcode_metadata=stable_readonly_suitcode.agent_metadata,
            stable_readonly_baseline_metadata=stable_readonly_baseline.agent_metadata,
            calibration_suitcode=(
                self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.CALIBRATION, calibration_suitcode)
                if calibration_suitcode is not None
                else None
            ),
            calibration_baseline=(
                self._arm_run_reference(EvaluationArm.BASELINE, SuiteRole.CALIBRATION, calibration_baseline)
                if calibration_baseline is not None
                else None
            ),
            calibration_suitcode_metadata=(calibration_suitcode.agent_metadata if calibration_suitcode is not None else None),
            calibration_baseline_metadata=(calibration_baseline.agent_metadata if calibration_baseline is not None else None),
            stable_execution_suitcode=(
                self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STABLE_EXECUTION, stable_execution_report)
                if stable_execution_report is not None
                else None
            ),
            stable_execution_baseline=(
                self._arm_run_reference(EvaluationArm.BASELINE, SuiteRole.STABLE_EXECUTION, stable_execution_baseline)
                if stable_execution_baseline is not None
                else None
            ),
            stable_execution_suitcode_metadata=(stable_execution_report.agent_metadata if stable_execution_report is not None else None),
            stable_execution_baseline_metadata=(stable_execution_baseline.agent_metadata if stable_execution_baseline is not None else None),
            stress_readonly_suitcode=(
                self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STRESS_READONLY, stress_report)
                if stress_report is not None
                else None
            ),
            stress_readonly_baseline=(
                self._arm_run_reference(EvaluationArm.BASELINE, SuiteRole.STRESS_READONLY, stress_baseline)
                if stress_baseline is not None
                else None
            ),
            stress_readonly_suitcode_metadata=(stress_report.agent_metadata if stress_report is not None else None),
            stress_readonly_baseline_metadata=(stress_baseline.agent_metadata if stress_baseline is not None else None),
            evaluation_scope=self._evaluation_scope(skip_stress=skip_stress, stress_report=stress_report, stress_baseline=stress_baseline),
            protocol=protocol,
            measured_metrics=metric_groups[MetricKind.MEASURED],
            estimated_metrics=metric_groups[MetricKind.ESTIMATED],
            derived_metrics=metric_groups[MetricKind.DERIVED],
            headline_deltas=self._headline_deltas(stable_readonly_suitcode, stable_readonly_baseline),
            stable_readonly_summary=self._summary_payload(stable_readonly_suitcode),
            stable_execution_summary=(self._summary_payload(stable_execution_report) if stable_execution_report is not None else None),
            stress_summary=(self._summary_payload(stress_report) if stress_report is not None else None),
            stress_baseline_summary=(self._summary_payload(stress_baseline) if stress_baseline is not None else None),
            passive_usage_summary=passive_summary,
            agent_experience_summary=agent_experience_summary,
            headline_efficiency=headline_efficiency,
            provenance_coverage=provenance_coverage,
            terminology=self._terminology(),
            suite_descriptions=suite_descriptions,
            arm_policies=arm_policies,
            suite_failure_explanations=suite_failure_explanations,
            task_level_summaries=task_level_summaries,
            evaluation_validity_notes=evaluation_validity_notes,
            methodology=self._methodology(
                spec,
                stable_timeout_seconds,
                stress_timeout_seconds,
                stable_readonly_tasks=stable_readonly_tasks,
                full_auto=full_auto,
                sandbox=sandbox,
                bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
            ),
            limitations=self._limitations(),
            repro_commands=self._repro_commands(
                spec,
                model=model,
                profile_suitcode=profile_suitcode,
                profile_baseline=profile_baseline,
                skip_execution=skip_execution,
                skip_stress=skip_stress,
            ),
        )

    def _load_tasks(self, relative_path: str, *, timeout_seconds: int | None) -> tuple:
        tasks_file = (self._working_directory / relative_path).expanduser().resolve()
        tasks = self._evaluation_service.load_tasks(tasks_file)
        if timeout_seconds is None:
            return tasks
        return tuple(item.model_copy(update={"timeout_seconds": timeout_seconds}) for item in tasks)

    def _baseline_disable_override(self) -> str:
        config_path = self._working_directory / ".codex" / "config.toml"
        if not config_path.exists():
            raise ValueError(f"Codex config not found for baseline arm: `{config_path}`")
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        mcp_servers = payload.get("mcp_servers")
        if not isinstance(mcp_servers, dict):
            raise ValueError(f"Codex config is missing `mcp_servers`: `{config_path}`")
        suitcode = mcp_servers.get("suitcode")
        if not isinstance(suitcode, dict):
            raise ValueError(f"Codex config is missing `mcp_servers.suitcode`: `{config_path}`")
        command = suitcode.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError(f"Codex config has invalid `mcp_servers.suitcode.command`: `{config_path}`")
        args = suitcode.get("args")
        if not isinstance(args, list) or not all(isinstance(item, str) and item.strip() for item in args):
            raise ValueError(f"Codex config has invalid `mcp_servers.suitcode.args`: `{config_path}`")
        transport = suitcode.get("transport")
        if not isinstance(transport, str) or not transport.strip():
            transport = "stdio"
        escaped_command = command.replace("'", "\\'")
        escaped_args = ",".join("'" + item.replace("'", "\\'") + "'" for item in args)
        return f"mcp_servers.suitcode={{transport='{transport}',command='{escaped_command}',args=[{escaped_args}],enabled=false}}"

    @staticmethod
    def _arm_run_reference(arm: EvaluationArm, suite_role: SuiteRole, report: CodexEvaluationReport) -> ArmRunReference:
        return ArmRunReference(
            arm=arm,
            suite_role=suite_role,
            report_id=report.report_id,
            task_total=report.task_total,
            task_passed=report.task_passed,
            task_failed=report.task_failed,
            task_error=report.task_error,
        )

    @staticmethod
    def _summary_payload(report: CodexEvaluationReport) -> dict[str, object]:
        return {
            "task_total": report.task_total,
            "task_passed": report.task_passed,
            "task_failed": report.task_failed,
            "task_error": report.task_error,
            "required_tool_success_rate": report.required_tool_success_rate,
            "high_value_tool_early_rate": report.high_value_tool_early_rate,
            "answer_schema_success_rate": report.answer_schema_success_rate,
            "deterministic_action_success_rate": report.deterministic_action_success_rate,
            "avg_duration_ms": report.avg_duration_ms,
            "avg_transcript_tokens": report.avg_transcript_tokens,
            "avg_tokens_before_first_suitcode_tool": report.avg_tokens_before_first_suitcode_tool,
            "avg_tokens_before_first_high_value_tool": report.avg_tokens_before_first_high_value_tool,
            "avg_first_suitcode_tool_index": report.avg_first_suitcode_tool_index,
            "avg_first_high_value_tool_index": report.avg_first_high_value_tool_index,
            "sessions_with_no_high_value_tool_rate": report.sessions_with_no_high_value_tool_rate,
            "failure_kind_mix": report.failure_kind_mix,
            "correlation_quality_mix": report.correlation_quality_mix,
        }

    def _agent_experience_summary(self, *, repository_root: Path, days: int) -> dict[str, object]:
        now = datetime.now(UTC)
        cutoff = now.replace(microsecond=0) - timedelta(days=days)
        session_filter = lambda item: session_matches_live_filters(
            item,
            cutoff=cutoff,
            exclude_test_artifacts=True,
        )
        event_filter = lambda item: event_matches_live_filters(
            item,
            cutoff=cutoff,
            exclude_test_artifacts=True,
            exclude_benchmark_events=True,
        )
        agents = {
            AgentKind.CODEX.value: self._summarize_native_agent(
                agent_kind=AgentKind.CODEX.value,
                repository_root=repository_root,
                session_filter=session_filter,
            ),
            AgentKind.CLAUDE.value: self._summarize_native_agent(
                agent_kind=AgentKind.CLAUDE.value,
                repository_root=repository_root,
                session_filter=session_filter,
            ),
            AgentKind.CURSOR.value: self._summarize_native_agent(
                agent_kind=AgentKind.CURSOR.value,
                repository_root=repository_root,
                session_filter=session_filter,
            ),
        }
        mcp_summary = self._mcp_aggregator.summary(
            repository_root=repository_root,
            include_global=False,
            event_filter=event_filter,
        ).model_dump(mode="json")
        mcp_tool_usage = self._mcp_aggregator.tool_usage(
            repository_root=repository_root,
            include_global=False,
            event_filter=event_filter,
        )
        mcp_events = self._mcp_aggregator.load_events(
            repository_root=repository_root,
            include_global=False,
            event_filter=event_filter,
        )
        return {
            "repository_root": str(repository_root),
            "window_days": days,
            "window_start_utc": cutoff.isoformat().replace("+00:00", "Z"),
            "window_end_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "filter_policy": {
                "exclude_test_artifacts": True,
                "exclude_benchmark_events": True,
                "include_global_mcp_stream": False,
                "native_session_cutoff_basis": "artifact.last_event_at",
            },
            "mcp_analytics": {
                **mcp_summary,
                "top_tool_usage": tuple(
                    {
                        "tool_name": item.tool_name,
                        "total_calls": item.total_calls,
                        "success_calls": item.success_calls,
                        "error_calls": item.error_calls,
                        "estimated_tokens": item.estimated_tokens,
                        "estimated_tokens_saved": item.estimated_tokens_saved,
                        "p95_duration_ms": item.p95_duration_ms,
                    }
                    for item in mcp_tool_usage[:5]
                ),
                "error_breakdown": self._live_error_breakdown(mcp_events),
            },
            "agents": agents,
            "notes": (
                "Native agent summaries are filtered by latest artifact activity within the window.",
                "Codex native sessions can still contain older conversation history if a long-lived session remained active during the window.",
                "Cursor per-tool ordering remains best-effort when native transcripts omit explicit tool events.",
            ),
        }

    @staticmethod
    def _live_error_breakdown(events: tuple[Any, ...]) -> tuple[dict[str, object], ...]:
        grouped: dict[tuple[str, str, str], dict[str, object]] = {}
        for event in events:
            if getattr(event, "status", None).value != "error":
                continue
            tool_name = str(getattr(event, "tool_name", "") or "-")
            error_class = str(getattr(event, "error_class", "") or "UnknownError")
            error_message = str(getattr(event, "error_message", "") or "-")
            key = (tool_name, error_class, error_message)
            current = grouped.get(key)
            if current is None:
                grouped[key] = {
                    "tool_name": tool_name,
                    "error_class": error_class,
                    "error_message": error_message,
                    "count": 1,
                }
            else:
                current["count"] = int(current["count"]) + 1
        ordered = sorted(
            grouped.values(),
            key=lambda item: (-int(item["count"]), str(item["tool_name"]), str(item["error_class"]), str(item["error_message"])),
        )
        return tuple(ordered[:10])

    def _summarize_native_agent(
        self,
        *,
        agent_kind: str,
        repository_root: Path,
        session_filter,
    ) -> dict[str, object]:
        if agent_kind == AgentKind.CODEX.value:
            summary = self._analytics_service.repository_summary(repository_root, session_filter=session_filter)
        elif agent_kind == AgentKind.CLAUDE.value:
            summary = self._claude_analytics_service.repository_summary(repository_root, session_filter=session_filter)
        elif agent_kind == AgentKind.CURSOR.value:
            summary = self._cursor_analytics_service.repository_summary(repository_root, session_filter=session_filter)
        else:
            raise ValueError(f"unsupported agent_kind: `{agent_kind}`")
        payload = summary.model_dump(mode="json")
        payload["top_tools"] = tuple(
            {
                "tool_name": item["tool_name"],
                "call_count": item["call_count"],
            }
            for item in payload.get("tool_usage", [])[:5]
        )
        notes = list(payload.get("notes", []))
        transcript_metrics = payload.get("transcript_metrics", {})
        if (
            isinstance(transcript_metrics, dict)
            and int(transcript_metrics.get("suitcode_tool_call_count") or 0) == 0
            and int(payload.get("sessions_using_suitcode") or 0) > 0
        ):
            notes.append(
                "Per-tool usage was synthesized from correlated MCP events because native transcripts did not expose explicit SuitCode tool calls."
            )
        payload["notes"] = tuple(dict.fromkeys(str(item).strip() for item in notes if str(item).strip()))
        payload["adoption_label"] = self._adoption_label(payload)
        return payload

    @staticmethod
    def _adoption_label(summary: dict[str, Any]) -> str:
        session_count = int(summary.get("session_count") or 0)
        sessions_using = int(summary.get("sessions_using_suitcode") or 0)
        first_index = summary.get("avg_first_suitcode_tool_index")
        tokens_before = summary.get("avg_tokens_before_first_suitcode_tool")
        if session_count <= 0:
            return "no_observed_sessions"
        if sessions_using <= 0:
            return "no_observed_suitcode_usage"
        if first_index is not None and float(first_index) > 10.0:
            return "late_adoption"
        if tokens_before is not None and float(tokens_before) > 10000.0:
            return "late_adoption"
        if sessions_using < session_count:
            return "partial_adoption"
        return "healthy_adoption"

    @staticmethod
    def _metric_groups(
        metric_definitions: tuple[MetricDefinition, ...],
    ) -> dict[MetricKind, tuple[MetricDefinition, ...]]:
        grouped: dict[MetricKind, list[MetricDefinition]] = {
            MetricKind.MEASURED: [],
            MetricKind.ESTIMATED: [],
            MetricKind.DERIVED: [],
        }
        for item in metric_definitions:
            grouped[item.metric_kind].append(item)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _evaluation_scope(
        *,
        skip_stress: bool,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
    ) -> dict[str, object]:
        return {
            "agent_scope": "codex_only",
            "benchmark_status": "neutral_ab_protocol_v7",
            "headline_scope": "stable_readonly_downstream_ab",
            "stress_included": stress_report is not None and not skip_stress,
            "stress_status": (
                "excluded_from_headline"
                if skip_stress or stress_report is None
                else ("ab_reported_separately" if stress_baseline is not None else "reported_separately")
            ),
            "token_accounting": "transcript_estimated_visible_content_only",
            "claim_scope": "workflow_completion_and_deterministic_action_correctness",
        }

    def _protocol(
        self,
        *,
        spec: CodexStandoutComparisonSpec,
        model: str | None,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        stable_readonly_suitcode: CodexEvaluationReport,
        calibration_suitcode: CodexEvaluationReport | None,
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_report: CodexEvaluationReport | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
        stable_timeout_seconds: int | None,
        stress_timeout_seconds: int | None,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
    ) -> BenchmarkProtocol:
        repository_profiles = self._repository_profiles(
            stable_readonly_tasks=stable_readonly_tasks,
            stable_readonly_suitcode=stable_readonly_suitcode,
            calibration_suitcode=calibration_suitcode,
            calibration_tasks=calibration_tasks,
            stable_execution_tasks=stable_execution_tasks,
            stress_tasks=stress_tasks,
        )
        task_protocols = self._task_protocols(
            stable_readonly_tasks=stable_readonly_tasks,
            calibration_tasks=calibration_tasks,
            stable_execution_tasks=stable_execution_tasks,
            stress_tasks=stress_tasks,
        )
        return BenchmarkProtocol(
            protocol_name="suitcode_codex_neutral_protocol_v7",
            agent_family="codex",
            agent_version=stable_readonly_suitcode.agent_metadata.cli_version if stable_readonly_suitcode.agent_metadata is not None else None,
            model_name=(model or (stable_readonly_suitcode.agent_metadata.model_name if stable_readonly_suitcode.agent_metadata is not None else None)),
            model_provider=stable_readonly_suitcode.agent_metadata.model_provider if stable_readonly_suitcode.agent_metadata is not None else None,
            conditions=self._benchmark_conditions(sandbox=sandbox, bypass_approvals_and_sandbox=bypass_approvals_and_sandbox),
            task_protocols=task_protocols,
            repository_profiles=repository_profiles,
            metric_definitions=self._metric_definitions(),
            timeout_policy=(
                f"stable_readonly/stable_execution={stable_timeout_seconds or spec.stable_timeout_seconds or 'default'}s; "
                f"stress={stress_timeout_seconds or spec.stress_timeout_seconds or 'default'}s"
            ),
            session_policy="Fresh Codex evaluation runs; current report classifies all task runs as cold.",
            cache_policy="No benchmark-owned persistent index; repository/workspace state is process-local and not reused across task protocols in the report semantics.",
            repo_state_policy="Repository checkout pinned to the recorded git commit for the run; report artifacts are regenerated from stored evaluation outputs.",
            hardware_os_notes=(
                stable_readonly_suitcode.agent_metadata.host_os if stable_readonly_suitcode.agent_metadata is not None else "host_os_unavailable",
                "Transcript token metrics are estimated from visible rollout content only.",
                (
                    "Stress A/B included in this protocol run."
                    if stress_report is not None and stress_baseline is not None
                    else ("Stress suite included in this protocol run." if stress_report is not None else "Stress suite excluded from this protocol run.")
                ),
                ("Calibration suite included in this protocol run." if calibration_tasks is not None else "Calibration suite not included in this protocol run."),
            ),
        )

    @staticmethod
    def _metric_definitions() -> tuple[MetricDefinition, ...]:
        return (
            MetricDefinition(
                metric_name="task_success_rate",
                metric_kind=MetricKind.MEASURED,
                unit="rate",
                description="Fraction of tasks that passed the benchmark scoring contract.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="answer_schema_success_rate",
                metric_kind=MetricKind.MEASURED,
                unit="rate",
                description="Fraction of tasks whose final answer satisfied the required JSON schema.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="avg_duration_ms",
                metric_kind=MetricKind.MEASURED,
                unit="ms",
                description="Average wall-clock duration per task.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="median_turns_per_stable_headline_task",
                metric_kind=MetricKind.MEASURED,
                unit="turns",
                description="Median tool-turn count per stable headline task.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="required_tool_success_rate",
                metric_kind=MetricKind.MEASURED,
                unit="rate",
                description="Fraction of tasks that satisfied the required tool-use contract for the evaluated arm.",
                reported_in_headline=False,
                is_primary=False,
            ),
            MetricDefinition(
                metric_name="deterministic_action_success_rate",
                metric_kind=MetricKind.MEASURED,
                unit="rate",
                description="Fraction of execution tasks that selected and executed the correct deterministic action successfully.",
                reported_in_headline=False,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="avg_transcript_tokens",
                metric_kind=MetricKind.ESTIMATED,
                unit="tokens",
                description="Average transcript-estimated visible token count per task.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="avg_tokens_before_first_suitcode_tool",
                metric_kind=MetricKind.ESTIMATED,
                unit="tokens",
                description="Average visible token count before the first SuitCode tool call when such a call occurred.",
                reported_in_headline=False,
                is_primary=False,
            ),
            MetricDefinition(
                metric_name="avg_tokens_before_first_high_value_tool",
                metric_kind=MetricKind.ESTIMATED,
                unit="tokens",
                description="Average visible token count before the first high-value SuitCode tool call when such a call occurred.",
                reported_in_headline=False,
                is_primary=False,
            ),
            MetricDefinition(
                metric_name="median_turns_to_correct_deterministic_action",
                metric_kind=MetricKind.DERIVED,
                unit="turns",
                description="Median tool-turn count for passed deterministic execution tasks in the treatment arm.",
                reported_in_headline=True,
                is_primary=True,
            ),
            MetricDefinition(
                metric_name="success_normalized_token_cost",
                metric_kind=MetricKind.DERIVED,
                unit="tokens_per_passed_task",
                description="Total transcript-estimated tokens divided by passed tasks.",
                reported_in_headline=True,
                is_primary=False,
            ),
            MetricDefinition(
                metric_name="success_normalized_time_cost",
                metric_kind=MetricKind.DERIVED,
                unit="ms_per_passed_task",
                description="Total duration divided by passed tasks.",
                reported_in_headline=True,
                is_primary=False,
            ),
            MetricDefinition(
                metric_name="late_suitcode_adoption",
                metric_kind=MetricKind.DERIVED,
                unit="boolean_label",
                description="Derived passive-analytics label indicating that the first SuitCode tool appeared late in the trajectory.",
                reported_in_headline=False,
                is_primary=False,
            ),
        )

    def _benchmark_conditions(
        self,
        *,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
    ) -> tuple[BenchmarkCondition, ...]:
        approval_mode = "dangerous_bypass" if bypass_approvals_and_sandbox else "never"
        return (
            BenchmarkCondition(
                name="treatment",
                arm=EvaluationArm.SUITCODE.value,
                native_agent_tools=("codex_exec", "filesystem", "shell", "mcp"),
                suitcode_enabled=True,
                suitcode_tools_available=True,
                prompt_policy="Neutral task statement shared with baseline; environment availability is the only arm difference.",
                sandbox_mode=sandbox,
                approval_mode=approval_mode,
                notes=("Same Codex CLI, model, schema, repo, and timeout budget as baseline.",),
            ),
            BenchmarkCondition(
                name="baseline",
                arm=EvaluationArm.BASELINE.value,
                native_agent_tools=("codex_exec", "filesystem", "shell"),
                suitcode_enabled=False,
                suitcode_tools_available=False,
                prompt_policy="Same neutral task statement and output schema as treatment; SuitCode disabled via config override.",
                sandbox_mode=sandbox,
                approval_mode=approval_mode,
                notes=("SuitCode disabled via --config mcp_servers.suitcode.enabled=false.",),
            ),
        )

    def _task_protocols(
        self,
        *,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
    ) -> tuple[TaskProtocol, ...]:
        all_tasks = list(stable_readonly_tasks)
        if calibration_tasks is not None:
            all_tasks.extend(calibration_tasks)
        if stable_execution_tasks is not None:
            all_tasks.extend(stable_execution_tasks)
        if stress_tasks is not None:
            all_tasks.extend(stress_tasks)
        return tuple(self._task_protocol(task) for task in all_tasks)

    def _task_protocol(self, task: CodexEvaluationTask) -> TaskProtocol:
        return TaskProtocol(
            task_id=task.task_id,
            task_family=task.task_family.value,
            task_taxonomy=TaskTaxonomy(task.task_taxonomy),
            repository_path=task.repository_path,
            difficulty=task.difficulty,
            run_temperature=RunTemperature.COLD,
            question=task.question,
            target_selector={str(key): str(value) for key, value in task.target_selector.items()},
            required_tools=task.expected_required_tools,
            expected_ground_truth_kind=GroundTruthKind(task.ground_truth_kind),
            expected_success_criteria=task.expected_success_criteria,
            notes=self._task_protocol_notes(task),
        )

    def _repository_profiles(
        self,
        *,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        stable_readonly_suitcode: CodexEvaluationReport,
        calibration_suitcode: CodexEvaluationReport | None,
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
    ) -> tuple[RepositoryProfile, ...]:
        repository_paths = {task.repository_path for task in stable_readonly_tasks}
        if calibration_tasks is not None:
            repository_paths.update(task.repository_path for task in calibration_tasks)
        if stable_execution_tasks is not None:
            repository_paths.update(task.repository_path for task in stable_execution_tasks)
        if stress_tasks is not None:
            repository_paths.update(task.repository_path for task in stress_tasks)
        if calibration_tasks is not None and calibration_suitcode is not None:
            summaries = self._task_explanations(
            suite_role=SuiteRole.CALIBRATION,
            arm=EvaluationArm.SUITCODE,
                report=calibration_suitcode,
                tasks=calibration_tasks,
            )
        else:
            summaries = self._task_explanations(
                suite_role=SuiteRole.STABLE_READONLY,
                arm=EvaluationArm.SUITCODE,
                report=stable_readonly_suitcode,
                tasks=stable_readonly_tasks,
            )
        profiles: list[RepositoryProfile] = []
        for repository_path in sorted(repository_paths):
            profiles.append(self._repository_profile(repository_path=repository_path, summaries=summaries))
        return tuple(profiles)

    def _repository_profile(
        self,
        *,
        repository_path: str,
        summaries: tuple[TaskFailureExplanation, ...],
    ) -> RepositoryProfile:
        orientation = next(
            (
                item
                for item in summaries
                if item.repository_path == repository_path and item.task_family == CodexTaskFamily.ORIENTATION.value
            ),
            None,
        )
        expected = orientation.expected_answer if orientation is not None else {}
        provider_ids = expected.get("provider_ids")
        providers = tuple(str(item) for item in provider_ids) if isinstance(provider_ids, list) else tuple()
        ecosystem = providers[0] if providers else ("python" if "python" in repository_path else "npm")
        language_hint = ecosystem
        build_tool = ecosystem
        architecture_basis = f"{ecosystem} provider-backed repository summary / manifest-derived architecture"
        test_discovery_basis = f"{ecosystem} provider-backed deterministic test discovery"
        quality_basis = f"{ecosystem} provider-backed deterministic quality tooling"
        notes: list[str] = []
        if orientation is None:
            notes.append("Profile derived without orientation-task summary.")
        if repository_path == ".":
            notes.append("This profile points to the live SuitCode repository checkout rather than a fixture repo.")
        resolved_path = (self._working_directory / repository_path).expanduser().resolve()
        file_count = self._count_repository_files(resolved_path)
        action_counts = self._repository_action_counts(resolved_path)
        return RepositoryProfile(
            repository_path=repository_path,
            ecosystem=ecosystem,
            language_hint=language_hint,
            approximate_file_count=file_count,
            component_count=(expected.get("component_count") if isinstance(expected.get("component_count"), int) else None),
            test_count=(expected.get("test_count") if isinstance(expected.get("test_count"), int) else None),
            deterministic_action_count=action_counts["total"],
            test_action_count=action_counts["test"],
            build_action_count=action_counts["build"],
            runner_action_count=action_counts["runner"],
            build_tool=build_tool,
            repository_shape=self._repository_shape(
                repository_path=repository_path,
                ecosystem=ecosystem,
                component_count=(expected.get("component_count") if isinstance(expected.get("component_count"), int) else None),
            ),
            architecture_basis=architecture_basis,
            test_discovery_basis=test_discovery_basis,
            quality_basis=quality_basis,
            notes=tuple(notes),
        )

    @staticmethod
    def _repository_shape(*, repository_path: str, ecosystem: str, component_count: int | None) -> str:
        if repository_path == ".":
            return "live project checkout"
        if ecosystem == "npm" and (component_count or 0) > 1:
            return "workspace monorepo fixture"
        if ecosystem == "python" and (component_count or 0) <= 1:
            return "single-service fixture"
        return "fixture repository"

    @staticmethod
    def _count_repository_files(root: Path) -> int | None:
        if not root.exists() or not root.is_dir():
            return None
        skipped = {".git", ".suit", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "node_modules", "dist", "build"}
        count = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skipped for part in path.parts):
                continue
            count += 1
        return count

    @staticmethod
    def _repository_action_counts(repository_root: Path) -> dict[str, int | None]:
        if not repository_root.exists() or not repository_root.is_dir():
            return {"total": None, "test": None, "build": None, "runner": None}
        try:
            workspace = Workspace(repository_root)
            repository = workspace.get_repository(repository_root)
            actions = repository.list_actions()
        except ValueError:
            return {"total": None, "test": None, "build": None, "runner": None}
        return {
            "total": len(actions),
            "test": sum(1 for action in actions if action.kind == ActionKind.TEST_EXECUTION),
            "build": sum(1 for action in actions if action.kind == ActionKind.BUILD_EXECUTION),
            "runner": sum(1 for action in actions if action.kind == ActionKind.RUNNER_EXECUTION),
        }

    @staticmethod
    def _task_taxonomy(task_family: CodexTaskFamily) -> TaskTaxonomy:
        if task_family == CodexTaskFamily.ORIENTATION:
            return TaskTaxonomy.ORIENTATION
        if task_family == CodexTaskFamily.TRUTH_COVERAGE:
            return TaskTaxonomy.TRUTH_COVERAGE
        if task_family == CodexTaskFamily.CHANGE_ANALYSIS:
            return TaskTaxonomy.IMPACT_ANALYSIS
        if task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
            return TaskTaxonomy.BUG_FIX_NAVIGATION
        if task_family == CodexTaskFamily.CI_DEBUGGING:
            return TaskTaxonomy.CI_DEBUGGING
        if task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return TaskTaxonomy.MINIMUM_VERIFIED_CHANGE_SET
        if task_family == CodexTaskFamily.UNSUPPORTED_ACTION_REASONING:
            return TaskTaxonomy.UNSUPPORTED_ACTION_REASONING
        if task_family == CodexTaskFamily.TEST_EXECUTION:
            return TaskTaxonomy.TEST_EXECUTION
        if task_family == CodexTaskFamily.BUILD_EXECUTION:
            return TaskTaxonomy.BUILD_EXECUTION
        return TaskTaxonomy.LOCALIZATION

    @staticmethod
    def _ground_truth_kind(task_family: CodexTaskFamily) -> GroundTruthKind:
        if task_family in {
            CodexTaskFamily.ORIENTATION,
            CodexTaskFamily.TRUTH_COVERAGE,
            CodexTaskFamily.CHANGE_ANALYSIS,
            CodexTaskFamily.BUG_FIX_NAVIGATION,
            CodexTaskFamily.CI_DEBUGGING,
            CodexTaskFamily.UNSUPPORTED_ACTION_REASONING,
        }:
            return GroundTruthKind.EXACT_FIELD_MATCH
        if task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return GroundTruthKind.EXACT_ID_SET_MATCH
        if task_family == CodexTaskFamily.TEST_EXECUTION:
            return GroundTruthKind.EXACT_ACTION_RESULT_MATCH
        if task_family == CodexTaskFamily.BUILD_EXECUTION:
            return GroundTruthKind.EXACT_ACTION_RESULT_MATCH
        return GroundTruthKind.EXACT_FIELD_MATCH

    @staticmethod
    def _expected_success_criteria(task_family: CodexTaskFamily) -> tuple[str, ...]:
        if task_family == CodexTaskFamily.ORIENTATION:
            return (
                "Return schema-valid JSON.",
                "Match repository summary fields exactly, including provider_ids and counts.",
                "Match overall truth availability exactly.",
            )
        if task_family == CodexTaskFamily.TRUTH_COVERAGE:
            return (
                "Return schema-valid JSON.",
                "Match per-domain availability exactly.",
                "Do not infer unsupported domains or downgrade available domains incorrectly.",
            )
        if task_family == CodexTaskFamily.CHANGE_ANALYSIS:
            return (
                "Return schema-valid JSON.",
                "Match owner/component/test/quality/evidence fields against deterministic analyze_change output.",
            )
        if task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return (
                "Return schema-valid JSON.",
                "Match included test/build/runner/quality ID sets exactly.",
                "Do not add extra validation surfaces.",
            )
        if task_family == CodexTaskFamily.TEST_EXECUTION:
            return (
                "Return schema-valid JSON.",
                "Select the correct deterministic test target.",
                "Report the actual execution result correctly.",
            )
        if task_family == CodexTaskFamily.BUILD_EXECUTION:
            return (
                "Return schema-valid JSON.",
                "Select the correct deterministic build target.",
                "Report the actual execution result correctly.",
            )
        if task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
            return (
                "Return schema-valid JSON.",
                "Match the deterministic file owner and related-test preview from get_file_owner and get_related_tests.",
            )
        if task_family == CodexTaskFamily.CI_DEBUGGING:
            return (
                "Return schema-valid JSON.",
                "Select the same first deterministic test or build target as the baseline.",
                "Match the describe_* command preview exactly.",
            )
        if task_family == CodexTaskFamily.UNSUPPORTED_ACTION_REASONING:
            return (
                "Return schema-valid JSON.",
                "Match deterministic action support status and available action kinds exactly.",
                "Match the truth-coverage-based reason code exactly.",
            )
        return ("Return schema-valid JSON.", "Match deterministic ground truth exactly.")

    @staticmethod
    def _task_protocol_notes(task: CodexEvaluationTask) -> tuple[str, ...]:
        notes = ["Tasks are classified as cold in this report revision."]
        if task.target_selector:
            notes.append("Task includes an explicit selector and deterministic ground truth is computed against that selector.")
        return tuple(notes)

    @staticmethod
    def _placeholder_result_for_task(task: CodexEvaluationTask) -> CodexEvaluationTaskResult:
        return CodexEvaluationTaskResult(
            task_id=task.task_id,
            task_family=task.task_family.value,
            status=EvaluationStatus.PASSED,
            repository_root=task.repository_path,
            duration_ms=0,
            required_tool_count=len(task.expected_required_tools),
            tool_selection=CodexComparisonService._placeholder_tool_selection(task),
            answer_score=CodexComparisonService._placeholder_answer_score(),
            action_score=CodexComparisonService._placeholder_action_score(),
            stdout_jsonl_path="-",
            output_last_message_path="-",
        )

    @staticmethod
    def _placeholder_tool_selection(task: CodexEvaluationTask):
        from suitcode.evaluation.models import ToolSelectionScore

        return ToolSelectionScore(
            required_tools_present=True,
            required_tool_names=task.expected_required_tools,
            used_tool_names=task.expected_required_tools,
            first_suitcode_tool=(task.expected_required_tools[0] if task.expected_required_tools else None),
            first_high_value_tool=(task.expected_high_value_tools[0] if task.expected_high_value_tools else None),
            first_high_value_tool_index=(1 if task.expected_high_value_tools else None),
            used_high_value_tool_early=bool(task.expected_high_value_tools),
        )

    @staticmethod
    def _placeholder_answer_score():
        from suitcode.evaluation.models import AnswerScore

        return AnswerScore(schema_valid=True)

    @staticmethod
    def _placeholder_action_score():
        from suitcode.evaluation.models import ActionScore

        return ActionScore(executed=False, matched_target=False)

    def _suite_descriptions(
        self,
        *,
        spec: CodexStandoutComparisonSpec,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
    ) -> tuple[SuiteDescription, ...]:
        descriptions = [
            SuiteDescription(
                suite_role=SuiteRole.STABLE_READONLY,
                suite_type="headline_ab",
                suite_file=spec.stable_readonly_tasks_file,
                headline_included=True,
                suitcode_only=False,
                purpose="Headline bounded A/B comparison for downstream developer tasks such as impact reasoning and minimum verified change sets.",
                    benchmark_role_explanation="This suite defines the main baseline-vs-treatment comparison and is the only suite used for the primary A/B claims in this revision.",
                task_ids=tuple(task.task_id for task in stable_readonly_tasks),
            )
        ]
        if calibration_tasks is not None:
            descriptions.append(
                SuiteDescription(
                    suite_role=SuiteRole.CALIBRATION,
                    suite_type="calibration",
                    suite_file=spec.calibration_tasks_file or "",
                    headline_included=False,
                    suitcode_only=False,
                    purpose="Supporting A/B calibration suite for orientation and truth-coverage on the headline repositories.",
                    benchmark_role_explanation="This suite characterizes repository grounding and provenance coverage but does not drive the headline pass-rate claim.",
                    task_ids=tuple(task.task_id for task in calibration_tasks),
                )
            )
        if stable_execution_tasks is not None:
            descriptions.append(
                SuiteDescription(
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    suite_type="execution_ab",
                    suite_file=spec.stable_execution_tasks_file,
                    headline_included=False,
                    suitcode_only=False,
                    purpose="A/B deterministic action suite for test/build target selection and execution.",
                    benchmark_role_explanation="This suite compares baseline and treatment on bounded execution tasks, but it remains secondary to the read-only headline A/B.",
                    task_ids=tuple(task.task_id for task in stable_execution_tasks),
                )
            )
        if stress_tasks is not None:
            descriptions.append(
                SuiteDescription(
                    suite_role=SuiteRole.STRESS_READONLY,
                    suite_type="stress",
                    suite_file=spec.stress_readonly_tasks_file,
                    headline_included=False,
                    suitcode_only=False,
                    purpose="Stress read-only suite for broader live-project complexity.",
                    benchmark_role_explanation="This suite is intentionally excluded from the headline A/B and is reported separately as a current stress boundary, with A/B results when both arms are available.",
                    task_ids=tuple(task.task_id for task in stress_tasks),
                )
            )
        return tuple(descriptions)

    def _terminology(self) -> tuple[TerminologyEntry, ...]:
        return (
            TerminologyEntry(
                term="Stable read-only",
                definition="The bounded headline suite of downstream non-mutating developer tasks used for the main A/B comparison.",
            ),
            TerminologyEntry(
                term="Calibration",
                definition="A supporting A/B suite of orientation and truth-coverage tasks used to characterize repository grounding and provenance coverage rather than drive the headline claim.",
            ),
            TerminologyEntry(
                term="Stable execution",
                definition="The bounded A/B suite of deterministic test/build execution tasks used to compare target selection and execution correctness.",
            ),
            TerminologyEntry(
                term="Stress read-only",
                definition="A harder live-project read-only suite used to show current limits, reported separately from the headline comparison.",
            ),
            TerminologyEntry(
                term="SuitCode arm",
                definition="Codex with the SuitCode MCP enabled. In this revision, the task prompt is neutral across arms and SuitCode availability is the primary environmental difference.",
            ),
            TerminologyEntry(
                term="Baseline arm",
                definition="Codex with the SuitCode MCP disabled through config override; it answers the same tasks with the same prompt and output schema but without SuitCode.",
            ),
            TerminologyEntry(
                term="Transcript-estimated tokens",
                definition="Token counts estimated from visible transcript content only. These numbers are useful for relative evaluation but are not billing-accurate vendor totals.",
            ),
            TerminologyEntry(
                term="Answer mismatch",
                definition="A scored task failure where the final JSON satisfied the schema but one or more fields differed from deterministic ground truth.",
            ),
            TerminologyEntry(
                term="Infrastructure failure",
                definition="A run failure caused by the agent CLI, timeouts, session-artifact resolution, usage limits, or other harness/runtime issues rather than repository reasoning.",
            ),
        )

    @staticmethod
    def _arm_policies() -> tuple[ArmPolicyDescription, ...]:
        return (
            ArmPolicyDescription(
                arm=EvaluationArm.SUITCODE,
                suitcode_enabled=True,
                tooling_policy="SuitCode MCP tools are available alongside the same native agent tools available to baseline.",
                baseline_isolation=None,
                prompt_policy="Uses the same neutral task statement and output schema as baseline; no SuitCode-specific workflow text is injected into the prompt.",
                scoring_policy="Evaluated on answer correctness, tool-use diagnostics, and deterministic action correctness when applicable.",
            ),
            ArmPolicyDescription(
                arm=EvaluationArm.BASELINE,
                suitcode_enabled=False,
                tooling_policy="SuitCode MCP is disabled through config override; other native agent tools remain unchanged.",
                baseline_isolation="Codex is invoked with --config mcp_servers.suitcode.enabled=false via a full server-disable override.",
                prompt_policy="Uses the same neutral task statement and output schema as treatment, without any SuitCode-specific instructions.",
                scoring_policy="Evaluated on the same answer correctness and execution correctness criteria as treatment, without requiring SuitCode-only tool traces.",
            ),
        )

    def _suite_failure_explanations(
        self,
        *,
        stable_readonly_suitcode: CodexEvaluationReport,
        stable_readonly_baseline: CodexEvaluationReport,
        calibration_suitcode: CodexEvaluationReport | None,
        calibration_baseline: CodexEvaluationReport | None,
        stable_execution_report: CodexEvaluationReport | None,
        stable_execution_baseline: CodexEvaluationReport | None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
        skip_stress: bool,
    ) -> tuple[SuiteFailureExplanation, ...]:
        explanations = [
            self._suite_failure_explanation(
                suite_role=SuiteRole.STABLE_READONLY,
                arm=EvaluationArm.SUITCODE,
                report=stable_readonly_suitcode,
            ),
            self._suite_failure_explanation(
                suite_role=SuiteRole.STABLE_READONLY,
                arm=EvaluationArm.BASELINE,
                report=stable_readonly_baseline,
            ),
        ]
        if calibration_suitcode is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.CALIBRATION,
                    arm=EvaluationArm.SUITCODE,
                    report=calibration_suitcode,
                )
            )
        if calibration_baseline is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.CALIBRATION,
                    arm=EvaluationArm.BASELINE,
                    report=calibration_baseline,
                )
            )
        if stable_execution_report is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    arm=EvaluationArm.SUITCODE,
                    report=stable_execution_report,
                )
            )
        if stable_execution_baseline is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    arm=EvaluationArm.BASELINE,
                    report=stable_execution_baseline,
                )
            )
        if stress_report is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.STRESS_READONLY,
                    arm=EvaluationArm.SUITCODE,
                    report=stress_report,
                )
            )
        if stress_baseline is not None:
            explanations.append(
                self._suite_failure_explanation(
                    suite_role=SuiteRole.STRESS_READONLY,
                    arm=EvaluationArm.BASELINE,
                    report=stress_baseline,
                )
            )
        elif skip_stress:
            explanations.append(
                SuiteFailureExplanation(
                    suite_role=SuiteRole.STRESS_READONLY,
                    arm=EvaluationArm.SUITCODE,
                    task_total=0,
                    task_passed=0,
                    task_failed=0,
                    task_error=0,
                    failure_kind_mix={},
                    plain_language_summary="Stress read-only was intentionally excluded from this report and does not affect the headline A/B result.",
                    interpretation_notes=(
                        "Stable Read-Only A/B baseline failures are unrelated to the skipped stress suite.",
                    ),
                )
            )
        return tuple(explanations)

    def _task_level_summaries(
        self,
        *,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        stable_readonly_suitcode: CodexEvaluationReport,
        stable_readonly_baseline: CodexEvaluationReport,
        calibration_tasks: tuple[CodexEvaluationTask, ...] | None,
        calibration_suitcode: CodexEvaluationReport | None,
        calibration_baseline: CodexEvaluationReport | None,
        stable_execution_tasks: tuple[CodexEvaluationTask, ...] | None,
        stable_execution_report: CodexEvaluationReport | None,
        stable_execution_baseline: CodexEvaluationReport | None,
        stress_tasks: tuple[CodexEvaluationTask, ...] | None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
    ) -> tuple[TaskFailureExplanation, ...]:
        summaries: list[TaskFailureExplanation] = []
        summaries.extend(
            self._task_explanations(
                suite_role=SuiteRole.STABLE_READONLY,
                arm=EvaluationArm.SUITCODE,
                report=stable_readonly_suitcode,
                tasks=stable_readonly_tasks,
            )
        )
        summaries.extend(
            self._task_explanations(
                suite_role=SuiteRole.STABLE_READONLY,
                arm=EvaluationArm.BASELINE,
                report=stable_readonly_baseline,
                tasks=stable_readonly_tasks,
            )
        )
        if calibration_tasks is not None and calibration_suitcode is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.CALIBRATION,
                    arm=EvaluationArm.SUITCODE,
                    report=calibration_suitcode,
                    tasks=calibration_tasks,
                )
            )
        if calibration_tasks is not None and calibration_baseline is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.CALIBRATION,
                    arm=EvaluationArm.BASELINE,
                    report=calibration_baseline,
                    tasks=calibration_tasks,
                )
            )
        if stable_execution_baseline is not None and stable_execution_tasks is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    arm=EvaluationArm.BASELINE,
                    report=stable_execution_baseline,
                    tasks=stable_execution_tasks,
                )
            )
        if stable_execution_report is not None and stable_execution_tasks is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    arm=EvaluationArm.SUITCODE,
                    report=stable_execution_report,
                    tasks=stable_execution_tasks,
                )
            )
        if stress_report is not None and stress_tasks is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.STRESS_READONLY,
                    arm=EvaluationArm.SUITCODE,
                    report=stress_report,
                    tasks=stress_tasks,
                )
            )
        if stress_baseline is not None and stress_tasks is not None:
            summaries.extend(
                self._task_explanations(
                    suite_role=SuiteRole.STRESS_READONLY,
                    arm=EvaluationArm.BASELINE,
                    report=stress_baseline,
                    tasks=stress_tasks,
                )
            )
        return tuple(summaries)

    def _evaluation_validity_notes(
        self,
        *,
        stable_readonly_baseline: CodexEvaluationReport,
        calibration_baseline: CodexEvaluationReport | None,
        stable_execution_report: CodexEvaluationReport | None,
        stable_execution_baseline: CodexEvaluationReport | None,
        stress_report: CodexEvaluationReport | None,
        stress_baseline: CodexEvaluationReport | None,
        skip_stress: bool,
    ) -> tuple[str, ...]:
        notes = [
            "The headline A/B result is determined entirely by the bounded downstream stable read-only suite.",
            "Stress-suite reporting does not affect the downstream headline A/B result.",
        ]
        if stable_readonly_baseline.failure_kind_mix.get(EvaluationFailureKind.ANSWER_MISMATCH.value, 0) == stable_readonly_baseline.task_total:
            notes.append(
                "Baseline headline tasks failed because they produced schema-valid but incorrect answers, not because of infrastructure failures."
            )
        if stable_readonly_baseline.task_error == 0:
            notes.append("Baseline headline tasks had zero task errors; all failures were scored task failures.")
        if calibration_baseline is not None:
            notes.append("Calibration results are reported separately and do not alter the headline pass rate.")
        if stable_execution_report is not None and stable_execution_baseline is not None:
            notes.append("Stable execution is compared A/B in this report revision rather than treatment-only.")
        if stress_report is not None and stress_baseline is not None:
            notes.append("Stress read-only is reported as a same-timeout supplementary A/B section and remains excluded from the headline claim.")
        elif skip_stress or stress_report is None:
            notes.append("Stress read-only was intentionally excluded from the current headline report.")
        return tuple(notes)

    def _suite_failure_explanation(
        self,
        *,
        suite_role: SuiteRole,
        arm: EvaluationArm,
        report: CodexEvaluationReport,
    ) -> SuiteFailureExplanation:
        return SuiteFailureExplanation(
            suite_role=suite_role,
            arm=arm,
            task_total=report.task_total,
            task_passed=report.task_passed,
            task_failed=report.task_failed,
            task_error=report.task_error,
            failure_kind_mix=report.failure_kind_mix,
            plain_language_summary=self._suite_failure_summary_text(suite_role=suite_role, arm=arm, report=report),
            interpretation_notes=self._suite_interpretation_notes(suite_role=suite_role, arm=arm, report=report),
        )

    def _task_explanations(
        self,
        *,
        suite_role: SuiteRole,
        arm: EvaluationArm,
        report: CodexEvaluationReport,
        tasks: tuple[CodexEvaluationTask, ...],
    ) -> tuple[TaskFailureExplanation, ...]:
        task_map = {task.task_id: task for task in tasks}
        return tuple(
            self._task_explanation(
                suite_role=suite_role,
                arm=arm,
                report_id=report.report_id,
                result=item,
                task=task_map.get(item.task_id),
            )
            for item in report.tasks
        )

    def _task_explanation(
        self,
        *,
        suite_role: SuiteRole,
        arm: EvaluationArm,
        report_id: str,
        result: CodexEvaluationTaskResult,
        task: CodexEvaluationTask | None,
    ) -> TaskFailureExplanation:
        transcript_tokens = result.transcript_token_breakdown.total_tokens if result.transcript_token_breakdown is not None else None
        failure_kind = result.failure_kind
        expected_answer, actual_answer = self._task_answers(result=result)
        field_value_differences = self._field_value_differences(result=result, expected_answer=expected_answer, actual_answer=actual_answer)
        return TaskFailureExplanation(
            task_id=result.task_id,
            suite_role=suite_role,
            arm=arm,
            task_family=result.task_family,
            task_taxonomy=TaskTaxonomy(task.task_taxonomy if task is not None else self._task_taxonomy(CodexTaskFamily(result.task_family)).value),
            ground_truth_kind=GroundTruthKind(task.ground_truth_kind if task is not None else self._ground_truth_kind(CodexTaskFamily(result.task_family)).value),
            expected_success_criteria=(task.expected_success_criteria if task is not None else self._expected_success_criteria(CodexTaskFamily(result.task_family))),
            run_temperature=RunTemperature.COLD,
            repository_profile_label=self._repository_profile_label(task.repository_path if task is not None else result.repository_root),
            repository_path=(task.repository_path if task is not None else result.repository_root),
            question=(task.question if task is not None and task.question is not None else self._task_question(task=task, result=result)),
            selector_summary=self._selector_summary(task),
            status=result.status,
            failure_kind=failure_kind,
            failure_summary=result.failure_summary,
            plain_language_explanation=self._task_failure_text(result=result),
            is_infrastructure_failure=(failure_kind in self._infrastructure_failures()) if failure_kind is not None else False,
            is_scoring_failure=(failure_kind in self._scoring_failures()) if failure_kind is not None else False,
            is_answer_failure=(failure_kind == EvaluationFailureKind.ANSWER_MISMATCH),
            transcript_tokens=transcript_tokens,
            turn_count=result.turn_count,
            duration_ms=result.duration_ms,
            expected_answer=expected_answer,
            actual_answer=actual_answer,
            field_value_differences=field_value_differences,
            report_id=report_id,
            stdout_jsonl_path=result.stdout_jsonl_path,
            rollout_artifact_path=result.rollout_artifact_path,
            output_last_message_path=result.output_last_message_path,
        )

    @staticmethod
    def _ensure_report_usable(report: CodexEvaluationReport, *, suite_label: str) -> None:
        usage_limit_count = report.failure_kind_mix.get("usage_limit", 0)
        if usage_limit_count > 0:
            raise RuntimeError(
                f"Codex usage limit was reached during {suite_label}; standout comparison is not valid until quota resets"
            )

    @staticmethod
    def _selector_summary(task: CodexEvaluationTask | None) -> str | None:
        if task is None or not task.target_selector:
            return None
        parts = [f"{key}={value}" for key, value in sorted(task.target_selector.items())]
        return ", ".join(parts)

    @staticmethod
    def _repository_profile_label(repository_path: str) -> str:
        return repository_path

    @staticmethod
    def _infrastructure_failures() -> set[EvaluationFailureKind]:
        return {
            EvaluationFailureKind.TIMEOUT,
            EvaluationFailureKind.CLI_ERROR,
            EvaluationFailureKind.USAGE_LIMIT,
            EvaluationFailureKind.SESSION_ARTIFACT_MISSING,
            EvaluationFailureKind.SESSION_CORRELATION_AMBIGUOUS,
            EvaluationFailureKind.UNEXPECTED_EXCEPTION,
        }

    @staticmethod
    def _scoring_failures() -> set[EvaluationFailureKind]:
        return {
            EvaluationFailureKind.REQUIRED_TOOLS_MISSING,
            EvaluationFailureKind.ARGUMENT_MISMATCH,
            EvaluationFailureKind.SCHEMA_VALIDATION_FAILED,
            EvaluationFailureKind.REQUIRED_ACTION_NOT_EXECUTED,
            EvaluationFailureKind.REQUIRED_ACTION_WRONG_TARGET,
        }

    def _suite_failure_summary_text(
        self,
        *,
        suite_role: SuiteRole,
        arm: EvaluationArm,
        report: CodexEvaluationReport,
    ) -> str:
        label = f"{suite_role.value} {arm.value}"
        if report.task_error:
            return f"{label} produced {report.task_error} task errors and {report.task_failed} task failures."
        if report.task_failed:
            return f"{label} produced {report.task_failed} scored task failures and no task errors."
        return f"{label} completed all {report.task_passed} tasks successfully."

    def _suite_interpretation_notes(
        self,
        *,
        suite_role: SuiteRole,
        arm: EvaluationArm,
        report: CodexEvaluationReport,
    ) -> tuple[str, ...]:
        notes: list[str] = []
        if suite_role == SuiteRole.STABLE_READONLY and arm == EvaluationArm.BASELINE and report.task_failed:
            notes.append("These baseline failures come from the bounded downstream headline suite itself and are not caused by skipping the stress suite.")
        if suite_role == SuiteRole.CALIBRATION:
            notes.append("Calibration results characterize repository grounding and do not change the headline A/B pass-rate claim.")
        if report.failure_kind_mix.get(EvaluationFailureKind.ANSWER_MISMATCH.value, 0):
            notes.append("Answer-mismatch failures mean the final JSON satisfied the schema but did not match deterministic ground truth.")
        if report.task_error == 0:
            notes.append("No infrastructure-level task errors were recorded for this suite.")
        return tuple(notes)

    def _task_failure_text(self, *, result: CodexEvaluationTaskResult) -> str:
        if result.status == EvaluationStatus.PASSED:
            return "The task completed successfully and matched the deterministic scoring contract."
        if result.failure_kind == EvaluationFailureKind.ANSWER_MISMATCH:
            return (
                "The final answer was schema-valid but mismatched deterministic ground truth. "
                f"Details: {result.failure_summary}."
            )
        if result.failure_kind == EvaluationFailureKind.SCHEMA_VALIDATION_FAILED:
            return f"The run completed, but the final answer did not satisfy the required output schema. Details: {result.failure_summary}."
        if result.failure_kind == EvaluationFailureKind.REQUIRED_TOOLS_MISSING:
            return f"The task did not use the required tool contract for this arm. Details: {result.failure_summary}."
        if result.failure_kind in self._infrastructure_failures():
            return f"The task failed due to run infrastructure rather than repository reasoning. Details: {result.failure_summary}."
        return result.failure_summary or "The task failed."

    def _task_answers(self, *, result: CodexEvaluationTaskResult) -> tuple[dict[str, object], dict[str, object] | None]:
        metadata_path = Path(result.output_last_message_path).resolve().parents[1] / "metadata.json"
        expected_answer: dict[str, object] = {}
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            baseline = payload.get("baseline")
            if isinstance(baseline, dict):
                expected_answer = {str(key): value for key, value in baseline.items()}
        if not expected_answer:
            expected_answer = {"_unavailable": "expected answer not available in task metadata"}
        actual_answer: dict[str, object] | None = None
        last_message_path = Path(result.output_last_message_path)
        if last_message_path.exists():
            text = last_message_path.read_text(encoding="utf-8").strip()
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    actual_answer = {str(key): value for key, value in parsed.items()}
        return expected_answer, actual_answer

    @staticmethod
    def _field_value_differences(
        *,
        result: CodexEvaluationTaskResult,
        expected_answer: dict[str, object],
        actual_answer: dict[str, object] | None,
    ) -> dict[str, dict[str, object]]:
        differences: dict[str, dict[str, object]] = {}
        actual_map = actual_answer or {}
        for field_name, matched in result.answer_score.field_matches.items():
            if matched:
                continue
            differences[field_name] = {
                "expected": expected_answer.get(field_name),
                "actual": actual_map.get(field_name),
            }
        for field_name in result.answer_score.missing_fields:
            differences.setdefault(
                field_name,
                {
                    "expected": expected_answer.get(field_name),
                    "actual": None,
                },
            )
        return differences

    @staticmethod
    def _task_question(*, task: CodexEvaluationTask | None, result: CodexEvaluationTaskResult) -> str:
        if task is not None and task.question is not None:
            return task.question
        family = task.task_family if task is not None else CodexTaskFamily(result.task_family)
        selector = task.target_selector if task is not None else {}
        if family == CodexTaskFamily.ORIENTATION:
            return "What is this repository, which providers does it use, and what is the top-level repository summary and overall truth availability?"
        if family == CodexTaskFamily.TRUTH_COVERAGE:
            return "How much of this repository's architecture, code, tests, quality, and actions are available and trustworthy?"
        if family == CodexTaskFamily.CHANGE_ANALYSIS:
            return f"What changes if this target is modified, and what evidence supports that? Target: {selector!r}"
        if family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return f"What is the minimum exact deterministic validation set for this target? Target: {selector!r}"
        if family == CodexTaskFamily.TEST_EXECUTION:
            return f"Which exact test target should run for this task, and what was the execution result? Target: {selector!r}"
        if family == CodexTaskFamily.BUILD_EXECUTION:
            return f"Which exact build target should run for this task, and what was the execution result? Target: {selector!r}"
        return f"What is the correct structured answer for task family `{result.task_family}`?"

    def _headline_deltas(
        self,
        suitcode_report: CodexEvaluationReport,
        baseline_report: CodexEvaluationReport,
    ) -> tuple[ComparisonDelta, ...]:
        metrics = (
            ("task_success_rate", self._success_rate(suitcode_report), self._success_rate(baseline_report), True),
            ("answer_schema_success_rate", suitcode_report.answer_schema_success_rate, baseline_report.answer_schema_success_rate, True),
            ("avg_transcript_tokens", suitcode_report.avg_transcript_tokens, baseline_report.avg_transcript_tokens, False),
            ("avg_duration_ms", suitcode_report.avg_duration_ms, baseline_report.avg_duration_ms, False),
            ("success_normalized_token_cost", self._success_normalized_token_cost(suitcode_report), self._success_normalized_token_cost(baseline_report), False),
            ("success_normalized_time_cost", self._success_normalized_time_cost(suitcode_report), self._success_normalized_time_cost(baseline_report), False),
        )
        return tuple(self._delta(name, suitcode_value, baseline_value, higher_is_better=higher_is_better) for name, suitcode_value, baseline_value, higher_is_better in metrics)

    @staticmethod
    def _success_rate(report: CodexEvaluationReport) -> float:
        return report.task_passed / report.task_total if report.task_total else 0.0

    @staticmethod
    def _success_normalized_token_cost(report: CodexEvaluationReport) -> float | None:
        if not report.task_passed or report.avg_transcript_tokens is None:
            return None
        return (report.avg_transcript_tokens * report.task_total) / report.task_passed

    @staticmethod
    def _success_normalized_time_cost(report: CodexEvaluationReport) -> float | None:
        if not report.task_passed:
            return None
        return (report.avg_duration_ms * report.task_total) / report.task_passed

    @staticmethod
    def _delta(
        metric_name: str,
        suitcode_value: float | int | None,
        baseline_value: float | int | None,
        *,
        higher_is_better: bool,
    ) -> ComparisonDelta:
        if suitcode_value is None or baseline_value is None:
            return ComparisonDelta(
                metric_name=metric_name,
                suitcode_value=suitcode_value,
                baseline_value=baseline_value,
                direction="not_comparable",
            )
        delta_absolute = float(suitcode_value) - float(baseline_value)
        delta_ratio = None if float(baseline_value) == 0.0 else delta_absolute / float(baseline_value)
        if delta_absolute == 0:
            direction = "same"
        elif (delta_absolute > 0 and higher_is_better) or (delta_absolute < 0 and not higher_is_better):
            direction = "better"
        else:
            direction = "worse"
        return ComparisonDelta(
            metric_name=metric_name,
            suitcode_value=suitcode_value,
            baseline_value=baseline_value,
            delta_absolute=delta_absolute,
            delta_ratio=delta_ratio,
            direction=direction,
        )

    @staticmethod
    def _methodology(
        spec: CodexStandoutComparisonSpec,
        stable_timeout_seconds: int | None,
        stress_timeout_seconds: int | None,
        *,
        stable_readonly_tasks: tuple[CodexEvaluationTask, ...],
        full_auto: bool,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
    ) -> dict[str, object]:
        headline_families = ", ".join(sorted({task.task_family.value for task in stable_readonly_tasks}))
        return {
            "stable_readonly_suite": spec.stable_readonly_tasks_file,
            "calibration_suite": spec.calibration_tasks_file,
            "stable_execution_suite": spec.stable_execution_tasks_file if spec.include_stable_execution else None,
            "stress_readonly_suite": spec.stress_readonly_tasks_file if spec.include_stress_readonly else None,
            "baseline_isolation": "codex exec with --config mcp_servers.suitcode.enabled=false",
            "codex_execution_mode": ("full_auto" if full_auto else "manual_sandbox"),
            "codex_sandbox": sandbox,
            "codex_bypass_approvals_and_sandbox": bypass_approvals_and_sandbox,
            "headline_comparison": f"headline downstream A/B ({headline_families}) with SuitCode arm vs baseline arm",
            "calibration_policy": "orientation and truth_coverage are reported as calibration A/B only",
            "execution_policy": "stable execution is A/B in this phase",
            "stress_policy": "stress read-only is reported separately from the headline claim and may be A/B when both stress arms are present",
            "token_metric_kind": "transcript_estimated",
            "stable_timeout_seconds": stable_timeout_seconds,
            "stress_timeout_seconds": stress_timeout_seconds,
        }

    @staticmethod
    def _limitations() -> tuple[str, ...]:
        return (
            "Transcript-estimated tokens are not billing-accurate vendor usage.",
            "The headline A/B comparison is limited to bounded downstream tasks on one live repo and one fixture repo in this phase.",
            "Calibration orientation/truth-coverage tasks are supporting evidence and are not part of the headline pass-rate claim.",
            "Stress read-only is supplementary and is not part of the headline A/B claim.",
            "Execution A/B remains fixture-backed in this phase for deterministic stability.",
        )

    def _repro_commands(
        self,
        spec: CodexStandoutComparisonSpec,
        *,
        model: str | None,
        profile_suitcode: str | None,
        profile_baseline: str | None,
        skip_execution: bool,
        skip_stress: bool,
    ) -> tuple[str, ...]:
        parts = ["python scripts/run_codex_comparison.py"]
        if model is not None:
            parts.extend(["--model", model])
        if profile_suitcode is not None:
            parts.extend(["--profile-suitcode", profile_suitcode])
        if profile_baseline is not None:
            parts.extend(["--profile-baseline", profile_baseline])
        if skip_execution:
            parts.append("--skip-execution")
        if skip_stress:
            parts.append("--skip-stress")
        commands = [
            " ".join(parts),
            "python scripts/analyze_codex_comparison.py --latest",
            f"python scripts/run_codex_eval.py --tasks-file {spec.stable_readonly_tasks_file}",
        ]
        if spec.calibration_tasks_file is not None:
            commands.append(f"python scripts/run_codex_eval.py --tasks-file {spec.calibration_tasks_file}")
        commands.append(f"python scripts/run_codex_eval.py --tasks-file {spec.stable_execution_tasks_file}")
        commands.append(f"python scripts/run_codex_eval.py --tasks-file {spec.stress_readonly_tasks_file}")
        return tuple(commands)

    @staticmethod
    def _format_markdown_value(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (str, int, float)):
            return str(value)
        if isinstance(value, (list, tuple)):
            return ", ".join(CodexComparisonService._format_markdown_value(item) for item in value) or "-"
        if isinstance(value, dict):
            ordered = []
            for key in sorted(value):
                ordered.append(f"{key}={CodexComparisonService._format_markdown_value(value[key])}")
            return "; ".join(ordered) or "-"
        return str(value)

    def _summary_rows(self, summary: dict[str, object]) -> tuple[tuple[str, str], ...]:
        rows = []
        for key in (
            "task_total",
            "task_passed",
            "task_failed",
            "task_error",
            "required_tool_success_rate",
            "high_value_tool_early_rate",
            "answer_schema_success_rate",
            "deterministic_action_success_rate",
            "avg_duration_ms",
            "avg_transcript_tokens",
        ):
            if key in summary:
                rows.append((key, self._format_markdown_value(summary[key])))
        return tuple(rows)

    @staticmethod
    def _summary_number(summary: dict[str, object], key: str) -> str:
        value = summary.get(key)
        if value is None:
            return "-"
        return str(value)

    @staticmethod
    def _summary_mapping(summary: dict[str, object], key: str) -> dict[str, object]:
        value = summary.get(key)
        if isinstance(value, dict):
            return {str(item_key): item_value for item_key, item_value in value.items()}
        return {}

    @staticmethod
    def _summary_sequence(summary: dict[str, object], key: str) -> list[dict[str, object]]:
        value = summary.get(key)
        if not isinstance(value, list):
            return []
        rows: list[dict[str, object]] = []
        for item in value:
            if isinstance(item, dict):
                rows.append({str(item_key): item_value for item_key, item_value in item.items()})
        return rows

    def _append_markdown_table(
        self,
        lines: list[str],
        *,
        headers: tuple[str, ...],
        rows: tuple[tuple[str, ...], ...],
    ) -> None:
        if not rows:
            return
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    @staticmethod
    def _append_figure_block(lines: list[str], figure) -> None:
        lines.append(f"### {figure.title}")
        lines.append("")
        lines.append(f"![{figure.title}]({figure.svg_relative_path})")
        lines.append("")
        lines.append(f"Metric kinds: `{', '.join(item.value for item in figure.metric_kinds)}`")
        lines.append(f"Caption: {figure.caption}")
        lines.append(f"Interpretation: {figure.interpretation}")
        lines.append(f"Data: `{figure.csv_relative_path}`")
        lines.append("")

    @staticmethod
    def _metric_rows(metrics: tuple[MetricDefinition, ...]) -> tuple[tuple[str, str, str, str, str], ...]:
        return tuple(
            (
                item.metric_name,
                item.metric_kind.value,
                item.unit,
                item.description,
                ("yes" if item.reported_in_headline else "no"),
            )
            for item in metrics
        )

    @staticmethod
    def _condition_rows(protocol: BenchmarkProtocol) -> tuple[tuple[str, str, str, str, str, str], ...]:
        return tuple(
            (
                item.name,
                item.arm,
                ("yes" if item.suitcode_enabled else "no"),
                ("yes" if item.suitcode_tools_available else "no"),
                ", ".join(item.native_agent_tools),
                item.prompt_policy,
            )
            for item in protocol.conditions
        )

    @staticmethod
    def _repository_profile_rows(protocol: BenchmarkProtocol) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
        return tuple(
            (
                item.repository_path,
                item.ecosystem,
                item.language_hint,
                item.repository_shape or "-",
                item.build_tool or "-",
                item.architecture_basis,
                item.test_discovery_basis,
                item.quality_basis,
            )
            for item in protocol.repository_profiles
        )

    @staticmethod
    def _repository_structural_complexity_rows(
        protocol: BenchmarkProtocol,
    ) -> tuple[tuple[str, str, str, str, str, str, str, str, str, str], ...]:
        return tuple(
            (
                item.repository_path,
                item.repository_shape or "-",
                str(item.approximate_file_count) if item.approximate_file_count is not None else "-",
                str(item.component_count) if item.component_count is not None else "-",
                str(item.test_count) if item.test_count is not None else "-",
                str(item.deterministic_action_count) if item.deterministic_action_count is not None else "-",
                str(item.test_action_count) if item.test_action_count is not None else "-",
                str(item.build_action_count) if item.build_action_count is not None else "-",
                str(item.runner_action_count) if item.runner_action_count is not None else "-",
                item.architecture_basis,
            )
            for item in protocol.repository_profiles
        )

    @staticmethod
    def _provenance_coverage_rows(
        coverage: tuple[ProvenanceCoverageSummary, ...],
    ) -> tuple[tuple[str, str, str, str, str, str, str, str, str], ...]:
        return tuple(
            (
                item.repository_path,
                str(item.evidence_entity_count),
                str(item.authoritative_count),
                str(item.derived_count),
                str(item.heuristic_count),
                f"{item.authoritative_ratio:.1%}",
                f"{item.derived_ratio:.1%}",
                f"{item.heuristic_ratio:.1%}",
                f"{item.deterministic_action_capability_count}/{item.deterministic_action_capability_total} ({item.deterministic_action_capability_ratio:.1%})",
            )
            for item in coverage
        )

    @staticmethod
    def _task_protocol_rows(protocol: BenchmarkProtocol) -> tuple[tuple[str, str, str, str, str, str, str, str], ...]:
        return tuple(
            (
                item.task_id,
                item.task_taxonomy.value,
                item.repository_path,
                item.difficulty,
                item.run_temperature.value,
                item.expected_ground_truth_kind.value,
                item.question,
                "; ".join(item.expected_success_criteria),
            )
            for item in protocol.task_protocols
        )

    @staticmethod
    def _median_or_dash(values: list[int | float | None]) -> str:
        filtered = [float(item) for item in values if item is not None]
        if not filtered:
            return "-"
        value = median(filtered)
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return numerator / denominator

    def _headline_efficiency(
        self,
        task_level_summaries: tuple[TaskFailureExplanation, ...],
    ) -> tuple[HeadlineEfficiencyMetric, ...]:
        stable_suitcode = [
            item for item in task_level_summaries
            if item.suite_role == SuiteRole.STABLE_READONLY and item.arm == EvaluationArm.SUITCODE
        ]
        stable_baseline = [
            item for item in task_level_summaries
            if item.suite_role == SuiteRole.STABLE_READONLY and item.arm == EvaluationArm.BASELINE
        ]
        execution_suitcode = [
            item for item in task_level_summaries
            if item.suite_role == SuiteRole.STABLE_EXECUTION
            and item.arm == EvaluationArm.SUITCODE
            and item.status == EvaluationStatus.PASSED
        ]
        execution_baseline = [
            item for item in task_level_summaries
            if item.suite_role == SuiteRole.STABLE_EXECUTION
            and item.arm == EvaluationArm.BASELINE
            and item.status == EvaluationStatus.PASSED
        ]
        return (
            HeadlineEfficiencyMetric(
                metric_name="Median turns per stable headline task",
                baseline_value=self._median_or_dash([item.turn_count for item in stable_baseline]),
                suitcode_value=self._median_or_dash([item.turn_count for item in stable_suitcode]),
                interpretation="Primary A/B efficiency metric for the bounded headline suite. Lower is better.",
                is_hero_metric=True,
            ),
            HeadlineEfficiencyMetric(
                metric_name="Median turns to correct deterministic action",
                baseline_value=self._median_or_dash([item.turn_count for item in execution_baseline]),
                suitcode_value=self._median_or_dash([item.turn_count for item in execution_suitcode]),
                interpretation="Stable execution is compared A/B in this revision using the same neutral task prompt and deterministic target-selection policy.",
            ),
            HeadlineEfficiencyMetric(
                metric_name="Median transcript-estimated tokens per stable headline task",
                baseline_value=self._median_or_dash([item.transcript_tokens for item in stable_baseline]),
                suitcode_value=self._median_or_dash([item.transcript_tokens for item in stable_suitcode]),
                interpretation="Supporting efficiency metric estimated from visible transcript content only.",
            ),
            HeadlineEfficiencyMetric(
                metric_name="Median duration (ms) per stable headline task",
                baseline_value=self._median_or_dash([item.duration_ms for item in stable_baseline]),
                suitcode_value=self._median_or_dash([item.duration_ms for item in stable_suitcode]),
                interpretation="Measured wall-clock cost for the bounded stable headline suite.",
            ),
        )

    def _provenance_coverage(
        self,
        *,
        task_level_summaries: tuple[TaskFailureExplanation, ...],
    ) -> tuple[ProvenanceCoverageSummary, ...]:
        summaries: list[ProvenanceCoverageSummary] = []
        for item in task_level_summaries:
            if item.suite_role != SuiteRole.CALIBRATION or item.arm != EvaluationArm.SUITCODE:
                continue
            if item.task_family != CodexTaskFamily.TRUTH_COVERAGE.value:
                continue
            actual = item.actual_answer or {}
            domain_payloads = []
            for domain_name in ("architecture", "code", "tests", "quality", "actions"):
                domain = actual.get(domain_name)
                if not isinstance(domain, dict):
                    raise ValueError(f"truth coverage task `{item.task_id}` is missing domain `{domain_name}`")
                for field_name in ("authoritative_count", "derived_count", "heuristic_count", "unavailable_count", "availability"):
                    if field_name not in domain:
                        raise ValueError(f"truth coverage task `{item.task_id}` domain `{domain_name}` is missing `{field_name}`")
                domain_payloads.append(domain)
            authoritative = sum(int(domain["authoritative_count"]) for domain in domain_payloads)
            derived = sum(int(domain["derived_count"]) for domain in domain_payloads)
            heuristic = sum(int(domain["heuristic_count"]) for domain in domain_payloads)
            evidence_entity_count = authoritative + derived + heuristic
            action_domain = actual["actions"]
            action_capability_total = 3
            action_capability_count = action_capability_total - int(action_domain["unavailable_count"])
            notes = (
                "Treatment-only trust metric derived from the structured get_truth_coverage output for this repository.",
                "Unavailable entities are excluded from provenance ratios and reflected separately through deterministic action capability coverage.",
            )
            summaries.append(
                ProvenanceCoverageSummary(
                    repository_profile_label=item.repository_profile_label,
                    repository_path=item.repository_path,
                    scope="calibration_treatment_truth_coverage",
                    evidence_entity_count=evidence_entity_count,
                    authoritative_count=authoritative,
                    derived_count=derived,
                    heuristic_count=heuristic,
                    authoritative_ratio=self._ratio(authoritative, evidence_entity_count),
                    derived_ratio=self._ratio(derived, evidence_entity_count),
                    heuristic_ratio=self._ratio(heuristic, evidence_entity_count),
                    deterministic_action_capability_count=action_capability_count,
                    deterministic_action_capability_total=action_capability_total,
                    deterministic_action_capability_ratio=self._ratio(action_capability_count, action_capability_total),
                    notes=notes,
                )
            )
        if not summaries:
            raise ValueError("no SuitCode truth-coverage task summaries were available for provenance coverage")
        return tuple(sorted(summaries, key=lambda item: item.repository_path))

    def _efficiency_rows(self, report: CodexStandoutReport) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            (
                item.metric_name,
                item.baseline_value,
                item.suitcode_value,
                item.interpretation,
            )
            for item in report.headline_efficiency
        )

    def _failure_taxonomy_summary_rows(self, report: CodexStandoutReport) -> tuple[tuple[str, str, str, str], ...]:
        baseline_items = [item for item in report.task_level_summaries if item.arm == EvaluationArm.BASELINE]
        suitcode_items = [item for item in report.task_level_summaries if item.arm == EvaluationArm.SUITCODE]

        def count(items: list[TaskFailureExplanation], *, predicate) -> int:
            return sum(1 for item in items if predicate(item))

        rows = (
            (
                "Answer correctness",
                str(count(baseline_items, predicate=lambda item: item.is_answer_failure)),
                str(count(suitcode_items, predicate=lambda item: item.is_answer_failure)),
                "Schema-valid answers that mismatched deterministic ground truth.",
            ),
            (
                "Tool use / scoring",
                str(count(baseline_items, predicate=lambda item: item.is_scoring_failure)),
                str(count(suitcode_items, predicate=lambda item: item.is_scoring_failure)),
                "Wrong tool contract, wrong selector arguments, or schema-level scoring failures.",
            ),
            (
                "Action correctness",
                str(count(baseline_items, predicate=lambda item: item.failure_kind in {EvaluationFailureKind.REQUIRED_ACTION_NOT_EXECUTED, EvaluationFailureKind.REQUIRED_ACTION_WRONG_TARGET})),
                str(count(suitcode_items, predicate=lambda item: item.failure_kind in {EvaluationFailureKind.REQUIRED_ACTION_NOT_EXECUTED, EvaluationFailureKind.REQUIRED_ACTION_WRONG_TARGET})),
                "Incorrect deterministic test/build action selection or execution outcome.",
            ),
            (
                "Infrastructure",
                str(count(baseline_items, predicate=lambda item: item.is_infrastructure_failure)),
                str(count(suitcode_items, predicate=lambda item: item.is_infrastructure_failure)),
                "Timeouts, CLI failures, session-artifact issues, usage limits, or harness exceptions.",
            ),
        )
        return rows

    def _ground_truth_rows(self, report: CodexStandoutReport) -> tuple[tuple[str, str, str, str, str, str], ...]:
        rows: list[tuple[str, str, str, str, str, str]] = []
        for item in report.task_level_summaries:
            rows.append(
                (
                    item.task_id,
                    item.task_family,
                    item.ground_truth_kind.value,
                    item.question,
                    self._expected_answer_summary(item),
                    self._acceptable_variants_summary(item),
                )
            )
        return tuple(rows)

    def _expected_answer_summary(self, item: TaskFailureExplanation) -> str:
        expected = item.expected_answer
        if item.task_family == CodexTaskFamily.ORIENTATION.value:
            return self._format_markdown_value(
                {
                    "provider_ids": expected.get("provider_ids"),
                    "component_count": expected.get("component_count"),
                    "test_count": expected.get("test_count"),
                    "quality_provider_count": expected.get("quality_provider_count"),
                    "overall_truth_availability": expected.get("overall_truth_availability"),
                }
            )
        if item.task_family == CodexTaskFamily.TRUTH_COVERAGE.value:
            return self._format_markdown_value(
                {
                    "overall_availability": expected.get("overall_availability"),
                    "architecture": expected.get("architecture", {}).get("availability") if isinstance(expected.get("architecture"), dict) else None,
                    "code": expected.get("code", {}).get("availability") if isinstance(expected.get("code"), dict) else None,
                    "tests": expected.get("tests", {}).get("availability") if isinstance(expected.get("tests"), dict) else None,
                    "quality": expected.get("quality", {}).get("availability") if isinstance(expected.get("quality"), dict) else None,
                    "actions": expected.get("actions", {}).get("availability") if isinstance(expected.get("actions"), dict) else None,
                }
            )
        if item.task_family == CodexTaskFamily.TEST_EXECUTION.value:
            return self._format_markdown_value(
                {
                    "selected_test_id": expected.get("selected_test_id"),
                    "execution_status": expected.get("execution_status"),
                    "passed": expected.get("passed"),
                    "failed": expected.get("failed"),
                }
            )
        if item.task_family == CodexTaskFamily.BUILD_EXECUTION.value:
            return self._format_markdown_value(
                {
                    "selected_action_id": expected.get("selected_action_id"),
                    "execution_status": expected.get("execution_status"),
                    "succeeded": expected.get("succeeded"),
                }
            )
        return self._format_markdown_value(expected)

    @staticmethod
    def _acceptable_variants_summary(item: TaskFailureExplanation) -> str:
        if item.ground_truth_kind == GroundTruthKind.EXACT_FIELD_MATCH:
            return "None in the current stable suite; exact field match required."
        if item.ground_truth_kind == GroundTruthKind.EXACT_ID_SET_MATCH:
            return "None in the current stable suite; exact ID-set match required."
        if item.ground_truth_kind == GroundTruthKind.EXACT_ACTION_RESULT_MATCH:
            return "None in the current stable suite; exact target and execution result required."
        return "No alternate variants defined in the current stable suite."

    def _append_passive_usage_section(self, lines: list[str], summary: dict[str, object]) -> None:
        lines.append("## Passive Codex Usage")
        lines.append("")
        lines.append(
            "These passive session analytics are supporting evidence only. They are not the headline benchmark source, "
            "but they help explain how often Codex adopted SuitCode early in real sessions."
        )
        lines.append("")
        overview_rows = (
            ("Repository root", self._summary_number(summary, "repository_root")),
            ("Observed sessions", self._summary_number(summary, "session_count")),
            ("Sessions using SuitCode", self._summary_number(summary, "sessions_using_suitcode")),
            ("Sessions without SuitCode", self._summary_number(summary, "sessions_without_suitcode")),
            ("Skipped artifacts", self._summary_number(summary, "skipped_artifacts")),
            ("Latest session id", self._summary_number(summary, "latest_session_id")),
            ("Latest session time", self._summary_number(summary, "latest_session_at")),
        )
        lines.append("### Session Overview")
        lines.append("")
        self._append_markdown_table(lines, headers=("Metric", "Value"), rows=overview_rows)

        adoption_rows = (
            ("Sessions with no high-value SuitCode tool", self._summary_number(summary, "sessions_without_high_value_suitcode")),
            ("Sessions with late SuitCode adoption", self._summary_number(summary, "sessions_with_late_suitcode_adoption")),
            ("Sessions with late high-value adoption", self._summary_number(summary, "sessions_with_late_high_value_adoption")),
            ("Sessions with shell-heavy pre-SuitCode exploration", self._summary_number(summary, "sessions_with_shell_heavy_pre_suitcode")),
            ("Average first SuitCode tool index", self._summary_number(summary, "avg_first_suitcode_tool_index")),
            ("Average first high-value tool index", self._summary_number(summary, "avg_first_high_value_tool_index")),
        )
        lines.append("### Adoption Timing")
        lines.append("")
        self._append_markdown_table(lines, headers=("Metric", "Value"), rows=adoption_rows)

        tool_usage_rows = []
        for item in self._summary_sequence(summary, "tool_usage")[:10]:
            tool_usage_rows.append(
                (
                    self._format_markdown_value(item.get("tool_name")),
                    self._format_markdown_value(item.get("call_count")),
                    self._format_markdown_value(item.get("first_seen_at")),
                    self._format_markdown_value(item.get("last_seen_at")),
                )
            )
        if tool_usage_rows:
            lines.append("### Most Used SuitCode Tools")
            lines.append("")
            self._append_markdown_table(
                lines,
                headers=("Tool", "Calls", "First seen", "Last seen"),
                rows=tuple(tool_usage_rows),
            )

        first_tool_distribution = self._summary_mapping(summary, "first_tool_distribution")
        if first_tool_distribution:
            lines.append("### First SuitCode Tool Distribution")
            lines.append("")
            rows = tuple(
                (tool_name, self._format_markdown_value(count))
                for tool_name, count in sorted(first_tool_distribution.items(), key=lambda item: (-int(item[1]), item[0]))
            )
            self._append_markdown_table(lines, headers=("Tool", "Sessions"), rows=rows)

        first_high_value_distribution = self._summary_mapping(summary, "first_high_value_tool_distribution")
        if first_high_value_distribution:
            lines.append("### First High-Value SuitCode Tool Distribution")
            lines.append("")
            rows = tuple(
                (tool_name, self._format_markdown_value(count))
                for tool_name, count in sorted(first_high_value_distribution.items(), key=lambda item: (-int(item[1]), item[0]))
            )
            self._append_markdown_table(lines, headers=("Tool", "Sessions"), rows=rows)

        correlation_quality_mix = self._summary_mapping(summary, "correlation_quality_mix")
        if correlation_quality_mix:
            lines.append("### Correlation Quality")
            lines.append("")
            rows = tuple(
                (quality, self._format_markdown_value(count))
                for quality, count in sorted(correlation_quality_mix.items(), key=lambda item: (-int(item[1]), item[0]))
            )
            self._append_markdown_table(lines, headers=("Quality", "Sessions"), rows=rows)

        token_rows = (
            ("Total transcript-estimated tokens", self._summary_number(summary, "total_tokens")),
            ("Average tokens per session", self._summary_number(summary, "avg_tokens_per_session")),
            ("Average tokens before first SuitCode tool", self._summary_number(summary, "avg_tokens_before_first_suitcode_tool")),
            ("Average tokens before first high-value tool", self._summary_number(summary, "avg_tokens_before_first_high_value_tool")),
        )
        lines.append("### Token Summary")
        lines.append("")
        self._append_markdown_table(lines, headers=("Metric", "Value"), rows=token_rows)

        token_breakdowns = self._summary_mapping(summary, "token_breakdowns_by_kind")
        if token_breakdowns:
            lines.append("### Token Breakdown by Visible Transcript Segment")
            lines.append("")
            rows = tuple(
                (segment_kind, self._format_markdown_value(count))
                for segment_kind, count in sorted(token_breakdowns.items())
            )
            self._append_markdown_table(lines, headers=("Segment kind", "Tokens"), rows=rows)

        transcript_metrics = self._summary_mapping(summary, "transcript_metrics")
        if transcript_metrics:
            lines.append("### Transcript Event Summary")
            lines.append("")
            rows = tuple(
                (metric_name, self._format_markdown_value(value))
                for metric_name, value in sorted(transcript_metrics.items())
            )
            self._append_markdown_table(lines, headers=("Metric", "Value"), rows=rows)

        notes = summary.get("notes")
        if isinstance(notes, (list, tuple)) and notes:
            lines.append("### Notes")
            lines.append("")
            for item in notes:
                lines.append(f"- {self._format_markdown_value(item)}")
            lines.append("")

    def _append_historical_passive_usage_summary(self, lines: list[str], summary: dict[str, object]) -> None:
        lines.append("## Historical Codex Passive Analytics")
        lines.append("")
        lines.append(
            "This is a compact historical Codex-only appendix for the `suit-code` repository. It is supporting context only: "
            "not part of the controlled A/B benchmark and not part of the live multi-agent `MyGamesAnywhere` analysis."
        )
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Value"),
            rows=(
                ("Repository root", self._summary_number(summary, "repository_root")),
                ("Observed sessions", self._summary_number(summary, "session_count")),
                ("Sessions using SuitCode", self._summary_number(summary, "sessions_using_suitcode")),
                ("Sessions without SuitCode", self._summary_number(summary, "sessions_without_suitcode")),
                ("Average first SuitCode tool index", self._summary_number(summary, "avg_first_suitcode_tool_index")),
                (
                    "Average tokens before first SuitCode tool",
                    self._summary_number(summary, "avg_tokens_before_first_suitcode_tool"),
                ),
                ("Latest session id", self._summary_number(summary, "latest_session_id")),
                ("Latest session time", self._summary_number(summary, "latest_session_at")),
            ),
        )
        lines.append("")
        tool_usage_rows = []
        for item in self._summary_sequence(summary, "tool_usage")[:5]:
            tool_usage_rows.append(
                (
                    self._format_markdown_value(item.get("tool_name")),
                    self._format_markdown_value(item.get("call_count")),
                )
            )
        if tool_usage_rows:
            lines.append("### Top Historical Tools")
            lines.append("")
            self._append_markdown_table(
                lines,
                headers=("Tool", "Calls"),
                rows=tuple(tool_usage_rows),
            )
            lines.append("")
        notes = summary.get("notes")
        if isinstance(notes, (list, tuple)) and notes:
            lines.append("### Historical Notes")
            lines.append("")
            for item in notes[:5]:
                lines.append(f"- {self._format_markdown_value(item)}")
            lines.append("")

    def _append_agent_experience_section(self, lines: list[str], summary: dict[str, object]) -> None:
        lines.append("## Live Multi-Agent Experience")
        lines.append("")
        lines.append(
            "These sections are generated from filtered live analytics rather than benchmark runs. They summarize how "
            "Codex, Claude Code, and Cursor used SuitCode on a real repository within the configured window."
        )
        lines.append("")
        lines.append("Interpretation rules:")
        lines.append("")
        lines.append("- `Live MCP Event Summary` is repository-level and combines all live SuitCode MCP calls on the repository in the filtered window.")
        lines.append("- Per-agent sections are built from native agent transcripts plus correlated SuitCode MCP analytics when available.")
        lines.append("- Per-agent token rows refer to native transcript-estimated tokens before the first SuitCode tool in that agent's own session, not to repository-wide MCP savings.")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Value"),
            rows=(
                ("Repository root", self._summary_number(summary, "repository_root")),
                ("Window days", self._summary_number(summary, "window_days")),
                ("Window start", self._summary_number(summary, "window_start_utc")),
                ("Window end", self._summary_number(summary, "window_end_utc")),
            ),
        )
        lines.append("")

        agents = summary.get("agents")
        if isinstance(agents, dict):
            lines.append("### Agent Attribution Summary")
            lines.append("")
            self._append_markdown_table(
                lines,
                headers=("Agent", "Observed SuitCode usage", "First observed tool", "Per-agent token metric", "Main issue"),
                rows=tuple(
                    (
                        agent_kind.capitalize(),
                        self._agent_usage_phrase(agent_summary),
                        self._agent_first_tool_phrase(agent_summary),
                        self._agent_token_phrase(agent_summary),
                        self._agent_issue_phrase(agent_summary),
                    )
                    for agent_kind in (AgentKind.CODEX.value, AgentKind.CLAUDE.value, AgentKind.CURSOR.value)
                    if isinstance((agent_summary := agents.get(agent_kind)), dict)
                ),
            )
            lines.append("")

        mcp_summary = self._summary_mapping(summary, "mcp_analytics")
        if mcp_summary:
            lines.append("### Live MCP Event Summary")
            lines.append("")
            self._append_markdown_table(
                lines,
                headers=("Metric", "Value"),
                rows=(
                    ("Total live calls", self._format_markdown_value(mcp_summary.get("total_calls"))),
                    ("Successful live calls", self._format_markdown_value(mcp_summary.get("success_calls"))),
                    ("Errored live calls", self._format_markdown_value(mcp_summary.get("error_calls"))),
                    ("Estimated tokens", self._format_markdown_value(mcp_summary.get("estimated_tokens"))),
                    ("Estimated tokens saved", self._format_markdown_value(mcp_summary.get("estimated_tokens_saved"))),
                ),
            )
            top_usage = mcp_summary.get("top_tool_usage")
            if isinstance(top_usage, (list, tuple)) and top_usage:
                lines.append("")
                lines.append("#### Most-Used Tools")
                lines.append("")
                self._append_markdown_table(
                    lines,
                    headers=("Tool", "Calls", "Success", "Error", "Estimated Tokens Saved", "P95 Duration (ms)"),
                    rows=tuple(
                        (
                            self._format_markdown_value(item.get("tool_name")),
                            self._format_markdown_value(item.get("total_calls")),
                            self._format_markdown_value(item.get("success_calls")),
                            self._format_markdown_value(item.get("error_calls")),
                            self._format_markdown_value(item.get("estimated_tokens_saved")),
                            self._format_markdown_value(item.get("p95_duration_ms")),
                        )
                        for item in top_usage
                    ),
                )
            error_breakdown = mcp_summary.get("error_breakdown")
            if isinstance(error_breakdown, (list, tuple)) and error_breakdown:
                lines.append("")
                lines.append("#### Error Breakdown")
                lines.append("")
                self._append_markdown_table(
                    lines,
                    headers=("Tool", "Error Class", "Count", "Representative Error"),
                    rows=tuple(
                        (
                            self._format_markdown_value(item.get("tool_name")),
                            self._format_markdown_value(item.get("error_class")),
                            self._format_markdown_value(item.get("count")),
                            self._format_markdown_value(item.get("error_message")),
                        )
                        for item in error_breakdown
                    ),
                )
            lines.append("")

        if isinstance(agents, dict):
            for agent_kind in (AgentKind.CODEX.value, AgentKind.CLAUDE.value, AgentKind.CURSOR.value):
                agent_summary = agents.get(agent_kind)
                if not isinstance(agent_summary, dict):
                    continue
                lines.append(f"### {agent_kind.capitalize()} Live Usage")
                lines.append("")
                self._append_markdown_table(
                    lines,
                    headers=("Metric", "Value"),
                    rows=(
                        ("Observed SuitCode usage", self._agent_usage_phrase(agent_summary)),
                        ("Evidence source", self._agent_evidence_phrase(agent_summary)),
                        ("First observed SuitCode tool", self._agent_first_tool_phrase(agent_summary)),
                        ("Adoption label", self._format_markdown_value(agent_summary.get("adoption_label"))),
                        ("Average first SuitCode tool index", self._format_markdown_value(agent_summary.get("avg_first_suitcode_tool_index"))),
                        (
                            "Per-agent token metric",
                            self._agent_token_phrase(agent_summary),
                        ),
                        ("Main issue", self._agent_issue_phrase(agent_summary)),
                    ),
                )
                first_distribution = self._summary_mapping(agent_summary, "first_tool_distribution")
                if first_distribution:
                    lines.append("")
                    lines.append("#### First Tool Distribution")
                    lines.append("")
                    self._append_markdown_table(
                        lines,
                        headers=("First SuitCode tool", "Observed sessions"),
                        rows=tuple(
                            (tool_name, self._format_markdown_value(count))
                            for tool_name, count in sorted(first_distribution.items(), key=lambda item: (-int(item[1]), item[0]))
                        ),
                    )
                top_tools = agent_summary.get("top_tools")
                if isinstance(top_tools, (list, tuple)) and top_tools:
                    lines.append("")
                    lines.append("#### Top Tools")
                    lines.append("")
                    self._append_markdown_table(
                        lines,
                        headers=("Tool", "Calls"),
                        rows=tuple(
                            (
                                self._format_markdown_value(item.get("tool_name")),
                                self._format_markdown_value(item.get("call_count")),
                            )
                            for item in top_tools
                        ),
                    )
                notes = agent_summary.get("notes")
                if isinstance(notes, (list, tuple)) and notes:
                    lines.append("")
                    for item in notes:
                        lines.append(f"- {self._format_markdown_value(item)}")
                lines.append("")

        notes = summary.get("notes")
        if isinstance(notes, (list, tuple)) and notes:
            lines.append("### Live Analytics Notes")
            lines.append("")
            for item in notes:
                lines.append(f"- {self._format_markdown_value(item)}")
            lines.append("")

    @staticmethod
    def _agent_usage_phrase(agent_summary: dict[str, object]) -> str:
        session_count = int(agent_summary.get("session_count") or 0)
        sessions_using = int(agent_summary.get("sessions_using_suitcode") or 0)
        if session_count <= 0:
            return "no observed live sessions"
        if sessions_using <= 0:
            return "no observed SuitCode usage"
        return f"{sessions_using}/{session_count} observed sessions used SuitCode"

    @staticmethod
    def _agent_first_tool_phrase(agent_summary: dict[str, object]) -> str:
        distribution = agent_summary.get("first_tool_distribution")
        if not isinstance(distribution, dict) or not distribution:
            return "-"
        tool_name, count = max(
            ((str(tool), int(value)) for tool, value in distribution.items()),
            key=lambda item: (item[1], item[0]),
        )
        return f"{tool_name} ({count})"

    @staticmethod
    def _agent_token_phrase(agent_summary: dict[str, object]) -> str:
        tokens = agent_summary.get("avg_tokens_before_first_suitcode_tool")
        if tokens is None:
            return "unavailable or not reliable in current artifacts"
        return f"{tokens} transcript-estimated tokens before first SuitCode tool"

    @staticmethod
    def _agent_evidence_phrase(agent_summary: dict[str, object]) -> str:
        notes = agent_summary.get("notes")
        note_text = " ".join(str(item) for item in notes) if isinstance(notes, (list, tuple)) else ""
        if "synthesized from correlated MCP events" in note_text:
            return "native transcript plus correlated MCP events"
        return "native transcript analytics"

    @staticmethod
    def _agent_issue_phrase(agent_summary: dict[str, object]) -> str:
        adoption_label = str(agent_summary.get("adoption_label") or "-")
        if adoption_label == "no_observed_sessions":
            return "no live usage available in the current filtered window"
        if adoption_label == "no_observed_suitcode_usage":
            return "SuitCode was not observed in the filtered live window"
        if adoption_label == "late_adoption":
            return "SuitCode appears late in the trajectory"
        if adoption_label == "partial_adoption":
            notes = agent_summary.get("notes")
            note_text = " ".join(str(item) for item in notes) if isinstance(notes, (list, tuple)) else ""
            if "synthesized from correlated MCP events" in note_text:
                return "partial adoption and native tool visibility is incomplete"
            return "partial adoption across observed sessions"
        return "no dominant issue observed"

    def _markdown_report(self, report: CodexStandoutReport) -> str:
        comparison_dir_name = self._comparison_reporter.report_directory_name(report)
        lines: list[str] = []
        lines.append("# Codex Standout Evaluation")
        lines.append("")
        lines.append(f"- Report id: `{report.report_id}`")
        lines.append(f"- Generated at: `{report.generated_at_utc}`")
        lines.append(f"- Model: `{report.model or 'default'}`")
        lines.append("- Report role: `canonical reviewer-facing report`")
        lines.append("- Reader guidance: This markdown is self-contained. Supporting files under `docs/evaluation/` and `scripts/EVALUATION.md` are internal protocol/operator references and are not required to interpret the benchmark result.")
        lines.append("")
        lines.append("## Table of Contents")
        lines.append("")
        lines.append("- [Chapter 1. Controlled A/B Benchmark (Codex Only)](#chapter-1-controlled-ab-benchmark-codex-only)")
        lines.append("- [Benchmark Figures](#benchmark-figures)")
        lines.append("- [Chapter 2. Live Usage Analytics](#chapter-2-live-usage-analytics)")
        lines.append("- [Live Multi-Agent Experience](#live-multi-agent-experience)")
        lines.append("- [Live Analytics Figures](#live-analytics-figures)")
        lines.append("- [Chapter 3. Detailed Benchmark Results and Appendices](#chapter-3-detailed-benchmark-results-and-appendices)")
        lines.append("- [Historical Codex Passive Analytics](#historical-codex-passive-analytics)")
        lines.append("- [Chapter 4. Methodology and Reproducibility](#chapter-4-methodology-and-reproducibility)")
        lines.append("")
        lines.append("## Chapter 1. Controlled A/B Benchmark (Codex Only)")
        lines.append("")
        lines.append(
            "This chapter contains the controlled Codex-only benchmark: prompt-neutral A/B evaluation, deterministic scoring, and benchmark-backed figures."
        )
        lines.append("")
        lines.append("## Evaluation Scope and Status")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Field", "Value"),
            rows=(
                ("Agent scope", self._format_markdown_value(report.evaluation_scope.get("agent_scope"))),
                ("Benchmark status", self._format_markdown_value(report.evaluation_scope.get("benchmark_status"))),
                ("Headline scope", self._format_markdown_value(report.evaluation_scope.get("headline_scope"))),
                ("Stress included", self._format_markdown_value(report.evaluation_scope.get("stress_included"))),
                ("Stress status", self._format_markdown_value(report.evaluation_scope.get("stress_status"))),
                ("Token accounting", self._format_markdown_value(report.evaluation_scope.get("token_accounting"))),
                ("Claim scope", self._format_markdown_value(report.evaluation_scope.get("claim_scope"))),
            ),
        )
        lines.append("")
        lines.append("## Agent Metadata")
        lines.append("")
        lines.append("| Arm | Agent | CLI | Model | Provider | OS | Transport | SuitCode | Sandbox | Profile | Git |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        if report.stable_readonly_suitcode_metadata is not None:
            meta = report.stable_readonly_suitcode_metadata
            lines.append(
                f"| SuitCode | {meta.agent_kind.value} | {meta.cli_name} {meta.cli_version or 'unknown'} | "
                f"{meta.model_name or 'unknown'} | {meta.model_provider or 'unknown'} | {meta.host_os} | "
                f"{meta.mcp_transport or 'none'} | yes | {meta.sandbox_mode or 'default'} | "
                f"{meta.profile_name or 'none'} | {meta.git_commit_hash or 'unknown'}@{meta.git_branch or 'unknown'} |"
            )
        if report.stable_readonly_baseline_metadata is not None:
            meta = report.stable_readonly_baseline_metadata
            lines.append(
                f"| Baseline | {meta.agent_kind.value} | {meta.cli_name} {meta.cli_version or 'unknown'} | "
                f"{meta.model_name or 'unknown'} | {meta.model_provider or 'unknown'} | {meta.host_os} | "
                f"{meta.mcp_transport or 'none'} | no | {meta.sandbox_mode or 'default'} | "
                f"{meta.profile_name or 'none'} | {meta.git_commit_hash or 'unknown'}@{meta.git_branch or 'unknown'} |"
            )
        lines.append("")
        lines.append("### Arm Execution Details")
        lines.append("")
        if report.stable_readonly_suitcode_metadata is not None:
            meta = report.stable_readonly_suitcode_metadata
            lines.append("#### SuitCode Arm")
            lines.append("")
            lines.append(f"- Working directory: `{meta.working_directory}`")
            lines.append(f"- Command prefix: `{ ' '.join(meta.command_prefix) if meta.command_prefix else 'unknown' }`")
            lines.append(f"- MCP transport: `{meta.mcp_transport or 'none'}`")
            lines.append("")
        if report.stable_readonly_baseline_metadata is not None:
            meta = report.stable_readonly_baseline_metadata
            lines.append("#### Baseline Arm")
            lines.append("")
            lines.append(f"- Working directory: `{meta.working_directory}`")
            lines.append(f"- Command prefix: `{ ' '.join(meta.command_prefix) if meta.command_prefix else 'unknown' }`")
            if meta.config_overrides:
                lines.append(f"- Config override: `{'; '.join(meta.config_overrides)}`")
            lines.append("")
        lines.append("These execution details are included for reproducibility. The rest of the report can be read without referring back to the command lines.")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        hero_metric = next((item for item in report.headline_efficiency if item.is_hero_metric), None)
        lines.append(
            f"- Headline core A/B: SuitCode `{report.stable_readonly_suitcode.task_passed}/{report.stable_readonly_suitcode.task_total}` "
            f"vs baseline `{report.stable_readonly_baseline.task_passed}/{report.stable_readonly_baseline.task_total}`"
        )
        if hero_metric is not None:
            lines.append(
                f"- Headline efficiency: `{hero_metric.metric_name}` baseline=`{hero_metric.baseline_value}` "
                f"vs SuitCode=`{hero_metric.suitcode_value}`"
            )
        if report.stable_execution_suitcode is not None:
            lines.append(
                f"- Stable execution A/B: SuitCode `{report.stable_execution_suitcode.task_passed}/{report.stable_execution_suitcode.task_total}`"
                + (
                    f" vs baseline `{report.stable_execution_baseline.task_passed}/{report.stable_execution_baseline.task_total}`"
                    if report.stable_execution_baseline is not None
                    else ""
                )
            )
            deterministic_metric = next(
                (item for item in report.headline_efficiency if item.metric_name == "Median turns to correct deterministic action"),
                None,
            )
            if deterministic_metric is not None:
                lines.append(
                    f"- Deterministic action efficiency: SuitCode `{deterministic_metric.suitcode_value}` turns median on the stable execution suite"
                )
        token_metric = next(
            (item for item in report.headline_efficiency if item.metric_name == "Median transcript-estimated tokens per stable headline task"),
            None,
        )
        if token_metric is not None:
            lines.append(
                f"- Supporting token evidence: baseline=`{token_metric.baseline_value}` vs SuitCode=`{token_metric.suitcode_value}` "
                "transcript-estimated visible tokens per stable headline task"
            )
        if report.provenance_coverage:
            authoritative_range = ", ".join(
                f"{item.repository_path}=`{item.authoritative_ratio:.1%}`" for item in report.provenance_coverage
            )
            lines.append(
                f"- Treatment provenance coverage: authoritative evidence ratio by headline repo is {authoritative_range}"
            )
        if report.stress_readonly_suitcode is not None:
            stress_line = (
                f"- Stress read-only: SuitCode `{report.stress_readonly_suitcode.task_passed}/{report.stress_readonly_suitcode.task_total}`"
            )
            if report.stress_readonly_baseline is not None:
                stress_line += (
                    f" vs baseline `{report.stress_readonly_baseline.task_passed}/{report.stress_readonly_baseline.task_total}`"
                )
            lines.append(stress_line)
        for note in report.evaluation_validity_notes:
            lines.append(f"- Validity note: {note}")
        lines.append("")
        lines.append("## Benchmark Protocol")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Field", "Value"),
            rows=(
                ("Protocol name", f"`{report.protocol.protocol_name}`"),
                ("Agent family", f"`{report.protocol.agent_family}`"),
                ("Agent version", f"`{report.protocol.agent_version or 'unknown'}`"),
                ("Model provider", f"`{report.protocol.model_provider or 'unknown'}`"),
                ("Timeout policy", report.protocol.timeout_policy),
                ("Session policy", report.protocol.session_policy),
                ("Cache policy", report.protocol.cache_policy),
                ("Repository state policy", report.protocol.repo_state_policy),
            ),
        )
        lines.append("")
        lines.append("### Conditions")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Condition", "Arm", "SuitCode enabled", "SuitCode tools", "Native tools", "Prompt policy"),
            rows=self._condition_rows(report.protocol),
        )
        lines.append("### Measured Metrics")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Kind", "Unit", "Description", "Headline"),
            rows=self._metric_rows(report.measured_metrics),
        )
        lines.append("### Estimated Metrics")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Kind", "Unit", "Description", "Headline"),
            rows=self._metric_rows(report.estimated_metrics),
        )
        lines.append("### Derived Metrics")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Kind", "Unit", "Description", "Headline"),
            rows=self._metric_rows(report.derived_metrics),
        )
        lines.append("### Task Taxonomy")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Task", "Taxonomy", "Repository", "Difficulty", "Temperature", "Ground truth", "Question", "Success criteria"),
            rows=self._task_protocol_rows(report.protocol),
        )
        lines.append("### Repository Profiles")
        lines.append("")
        lines.append("These rows summarize the evaluated repositories as benchmark subjects: ecosystem, shape, and truth-source basis.")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Repository", "Ecosystem", "Language", "Shape", "Build tool", "Architecture basis", "Test basis", "Quality basis"),
            rows=self._repository_profile_rows(report.protocol),
        )
        lines.append("### Repository Structural Complexity")
        lines.append("")
        lines.append(
            "This table makes the bounded benchmark concrete. It reports hard structural counts and deterministic action-space size for the repositories used in the current headline and execution suites."
        )
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Repository", "Shape", "Files", "Components / Packages", "Tests", "Deterministic Actions", "Test Actions", "Build Actions", "Runner Actions", "Architecture Truth Source"),
            rows=self._repository_structural_complexity_rows(report.protocol),
        )
        lines.append("### Terminology")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Term", "Definition"),
            rows=tuple((item.term, item.definition) for item in report.terminology),
        )
        lines.append("")
        lines.append("## Baseline vs Treatment Definition")
        lines.append("")
        lines.append("The baseline and treatment conditions use the same Codex CLI, model family, repository state, and schema contract. The only intentional difference is whether SuitCode MCP capabilities are available.")
        lines.append("")
        lines.append("| Condition | Native agent tools | SuitCode tools | Goal |")
        lines.append("| --- | --- | --- | --- |")
        for item in report.protocol.conditions:
            goal = (
                "repo intelligence via SuitCode"
                if item.suitcode_enabled
                else "default Codex-native repository exploration"
            )
            lines.append(
                f"| {item.name} | {', '.join(item.native_agent_tools)} | "
                f"{'yes' if item.suitcode_tools_available else 'no'} | {goal} |"
            )
        lines.append("## Suite Inventory")
        lines.append("")
        lines.append("| Suite | Type | File | Headline A/B | SuitCode-only | Purpose | Benchmark role | Tasks |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for suite in report.suite_descriptions:
            lines.append(
                f"| {suite.suite_role.value} | {suite.suite_type} | {suite.suite_file} | {self._format_markdown_value(suite.headline_included)} | "
                f"{self._format_markdown_value(suite.suitcode_only)} | {suite.purpose} | {suite.benchmark_role_explanation} | {', '.join(suite.task_ids)} |"
            )
        lines.append("")
        lines.append("## Arm Policies")
        lines.append("")
        lines.append("| Arm | SuitCode enabled | Tooling policy | Prompt policy | Scoring policy | Baseline isolation |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for policy in report.arm_policies:
            lines.append(
                f"| {policy.arm.value} | {self._format_markdown_value(policy.suitcode_enabled)} | "
                f"{policy.tooling_policy} | {policy.prompt_policy} | {policy.scoring_policy} | "
                f"{policy.baseline_isolation or '-'} |"
            )
        lines.append("")
        lines.append("## Headline A/B: Downstream Developer Tasks")
        lines.append("")
        lines.append("This is the primary comparison table for the bounded downstream headline suite. The tasks are change-impact and minimum-verified-validation questions on one live repo and one fixture repo, using the same prompt and output schema across arms.")
        lines.append("")
        lines.append("| Metric | SuitCode | Baseline | Delta | Direction |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for delta in report.headline_deltas:
            delta_value = "-" if delta.delta_absolute is None else f"{delta.delta_absolute:.3f}"
            lines.append(
                f"| {delta.metric_name} | {delta.suitcode_value if delta.suitcode_value is not None else '-'} "
                f"| {delta.baseline_value if delta.baseline_value is not None else '-'} | {delta_value} | {delta.direction} |"
            )
        lines.append("")
        lines.append("## Deterministic Workflow Efficiency")
        lines.append("")
        lines.append(
            "Turns are treated as the primary efficiency metric in this revision because they are more stable across vendors and more closely match SuitCode's goal: compressing the path to the correct bounded answer or deterministic validation action."
        )
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Metric", "Baseline", "SuitCode", "Interpretation"),
            rows=self._efficiency_rows(report),
        )
        lines.append("")
        lines.append("## Provenance Coverage (SuitCode Treatment Only)")
        lines.append("")
        lines.append(
            "This section quantifies the explicit provenance surface returned by the SuitCode treatment arm. It is treatment-only on purpose: the baseline condition does not expose a structured provenance channel, so forcing an A/B provenance ratio would weaken the report."
        )
        lines.append("")
        lines.append("Coverage formulas:")
        lines.append("")
        lines.append("- `evidence_entity_count = authoritative_count + derived_count + heuristic_count`")
        lines.append("- `authoritative_ratio = authoritative_count / evidence_entity_count`")
        lines.append("- `derived_ratio = derived_count / evidence_entity_count`")
        lines.append("- `heuristic_ratio = heuristic_count / evidence_entity_count`")
        lines.append("- `deterministic_action_capability_ratio = available_action_capabilities / 3` for `{tests, builds, runners}`")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Repository", "Evidence-bearing Entities", "Authoritative", "Derived", "Heuristic", "Authoritative Ratio", "Derived Ratio", "Heuristic Ratio", "Deterministic Action Capability Ratio"),
            rows=self._provenance_coverage_rows(report.provenance_coverage),
        )
        lines.append("")
        if report.figures:
            benchmark_figures = tuple(
                item for item in report.figures if item.source_scope not in {"agent_experience", "passive_usage"}
            )
            analytics_figures = tuple(
                item for item in report.figures if item.source_scope in {"agent_experience", "passive_usage"}
            )
            if benchmark_figures:
                lines.append("## Benchmark Figures")
                lines.append("")
                lines.append("These figures are generated from the controlled Codex comparison artifacts. The plotted values are exported alongside them under `figures/data/*.csv`.")
                lines.append("")
                main_figures = tuple(item for item in benchmark_figures if item.section.value == 'main')
                supporting_figures = tuple(item for item in benchmark_figures if item.section.value == 'supporting')
                if main_figures:
                    lines.append("### Main Benchmark Figures")
                    lines.append("")
                    for figure in main_figures:
                        self._append_figure_block(lines, figure)
                if supporting_figures:
                    lines.append("### Supporting Benchmark Figures")
                    lines.append("")
                    for figure in supporting_figures:
                        self._append_figure_block(lines, figure)
        if report.agent_experience_summary is not None:
            lines.append("## Chapter 2. Live Usage Analytics")
            lines.append("")
            lines.append(
                "This chapter is separate from the controlled benchmark. It reports filtered live SuitCode usage on real repositories across Codex, Claude Code, and Cursor."
            )
            lines.append("")
            if report.agent_experience_summary is not None:
                self._append_agent_experience_section(lines, report.agent_experience_summary)
            if report.figures:
                analytics_figures = tuple(
                    item for item in report.figures if item.source_scope == "agent_experience"
                )
                if analytics_figures:
                    lines.append("## Live Analytics Figures")
                    lines.append("")
                    lines.append("These figures are generated from filtered live analytics rather than benchmark tasks.")
                    lines.append("")
                    main_figures = tuple(item for item in analytics_figures if item.section.value == 'main')
                    supporting_figures = tuple(item for item in analytics_figures if item.section.value == 'supporting')
                    if main_figures:
                        lines.append("### Main Live Figures")
                        lines.append("")
                        for figure in main_figures:
                            self._append_figure_block(lines, figure)
                    if supporting_figures:
                        lines.append("### Supporting Live Figures")
                        lines.append("")
                        for figure in supporting_figures:
                            self._append_figure_block(lines, figure)
        lines.append("## Chapter 3. Detailed Benchmark Results and Appendices")
        lines.append("")
        lines.append(
            "This chapter expands the controlled Codex benchmark with execution, calibration, stress, failure analysis, ground truth, and task-level details."
        )
        lines.append("")
        if report.stable_execution_summary is not None:
            lines.append("## Stable Execution A/B")
            lines.append("")
            lines.append("This section reports bounded execution tasks for both arms. Baseline is allowed to attempt target selection and execution under the same neutral task prompt; SuitCode is not given a treatment-only execution showcase anymore.")
            lines.append("")
            lines.append("| Metric | SuitCode | Baseline |")
            lines.append("| --- | ---: | ---: |")
            baseline_execution_summary = {
                "task_total": report.stable_execution_baseline.task_total if report.stable_execution_baseline is not None else None,
                "task_passed": report.stable_execution_baseline.task_passed if report.stable_execution_baseline is not None else None,
                "task_failed": report.stable_execution_baseline.task_failed if report.stable_execution_baseline is not None else None,
                "task_error": report.stable_execution_baseline.task_error if report.stable_execution_baseline is not None else None,
            }
            for key, value in self._summary_rows(report.stable_execution_summary):
                lines.append(
                    f"| {key} | {value} | {self._summary_number(baseline_execution_summary, key)} |"
                )
            lines.append("")
        if report.calibration_suitcode is not None and report.calibration_baseline is not None:
            lines.append("## Calibration Suite")
            lines.append("")
            lines.append("Calibration tasks are orientation and truth-coverage tasks on the headline repositories. They support repository characterization and treatment-only provenance coverage, but they do not contribute to the headline A/B claim.")
            lines.append("")
            lines.append("| Metric | SuitCode | Baseline |")
            lines.append("| --- | ---: | ---: |")
            calibration_summary = {
                "task_total": report.calibration_suitcode.task_total,
                "task_passed": report.calibration_suitcode.task_passed,
                "task_failed": report.calibration_suitcode.task_failed,
                "task_error": report.calibration_suitcode.task_error,
            }
            baseline_calibration_summary = {
                "task_total": report.calibration_baseline.task_total,
                "task_passed": report.calibration_baseline.task_passed,
                "task_failed": report.calibration_baseline.task_failed,
                "task_error": report.calibration_baseline.task_error,
            }
            for key, value in self._summary_rows(calibration_summary):
                lines.append(
                    f"| {key} | {value} | {self._summary_number(baseline_calibration_summary, key)} |"
                )
            lines.append("")
        if report.stress_summary is not None:
            lines.append("## Stress Read-Only")
            lines.append("")
            if report.stress_baseline_summary is not None:
                lines.append("This supplementary section reports stress read-only A/B under the same timeout budget for both arms. It remains outside the headline claim because the stress suite is intentionally broader and noisier than the bounded headline tasks.")
                lines.append("")
                lines.append("| Metric | SuitCode | Baseline |")
                lines.append("| --- | ---: | ---: |")
                for key, value in self._summary_rows(report.stress_summary):
                    lines.append(
                        f"| {key} | {value} | {self._summary_number(report.stress_baseline_summary, key)} |"
                    )
            else:
                lines.append("| Metric | Value |")
                lines.append("| --- | ---: |")
                for key, value in self._summary_rows(report.stress_summary):
                    lines.append(f"| {key} | {value} |")
            lines.append("")
        if report.passive_usage_summary is not None:
            self._append_historical_passive_usage_summary(lines, report.passive_usage_summary)
            if report.figures:
                passive_figures = tuple(item for item in report.figures if item.source_scope == "passive_usage")
                if passive_figures:
                    lines.append("## Historical Passive Figures")
                    lines.append("")
                    lines.append("These figures are generated from the historical Codex passive analytics summary for the `suit-code` repository.")
                    lines.append("")
                    for figure in passive_figures:
                        self._append_figure_block(lines, figure)
        lines.append("## Failure Taxonomy Summary")
        lines.append("")
        lines.append("Failure counts below are aggregated across the tasks included in this report. They distinguish substantive task failures from harness or account-state failures and explain where extra turns came from.")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Failure class", "Baseline count", "SuitCode count", "Notes"),
            rows=self._failure_taxonomy_summary_rows(report),
        )
        lines.append("")
        lines.append("## Failure Taxonomy")
        lines.append("")
        lines.append("| Failure kind | Category | Meaning | Counted as benchmark failure |")
        lines.append("| --- | --- | --- | --- |")
        failure_rows = (
            ("answer_mismatch", "answer_correctness", "Schema-valid answer with one or more fields differing from deterministic ground truth.", "yes"),
            ("schema_validation_failed", "tool_use_or_output", "Run completed but final answer did not satisfy the required schema.", "yes"),
            ("required_tools_missing", "tool_use_or_output", "Required tool-use contract was not followed for the evaluated arm.", "yes"),
            ("argument_mismatch", "tool_use_or_output", "Required tool was used with incorrect task-defining arguments.", "yes"),
            ("required_action_not_executed", "action_correctness", "Execution task did not run the required deterministic action.", "yes"),
            ("required_action_wrong_target", "action_correctness", "Execution task ran the wrong deterministic action target.", "yes"),
            ("timeout", "infrastructure", "Run hit the configured timeout budget.", "no"),
            ("cli_error", "infrastructure", "Codex CLI failed before a valid task result was produced.", "no"),
            ("usage_limit", "infrastructure", "Agent usage quota prevented a valid run; comparison is invalid.", "no"),
            ("session_artifact_missing", "infrastructure", "Expected rollout/session artifact could not be resolved.", "no"),
            ("session_correlation_ambiguous", "infrastructure", "Multiple candidate artifacts prevented deterministic attribution.", "no"),
            ("unexpected_exception", "infrastructure", "Harness-side unexpected exception rather than repository reasoning failure.", "no"),
        )
        for row in failure_rows:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
        lines.append("")
        lines.append("## Suite Failure Analysis")
        lines.append("")
        lines.append("| Suite | Arm | Passed | Failed | Errored | Failure kinds | Meaning |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for explanation in report.suite_failure_explanations:
            lines.append(
                f"| {explanation.suite_role.value} | {explanation.arm.value} | {explanation.task_passed} | "
                f"{explanation.task_failed} | {explanation.task_error} | "
                f"{self._format_markdown_value(explanation.failure_kind_mix)} | {explanation.plain_language_summary} |"
            )
            for note in explanation.interpretation_notes:
                lines.append(f"- Note for `{explanation.suite_role.value}/{explanation.arm.value}`: {note}")
        lines.append("")
        lines.append("## Ground Truth Appendix")
        lines.append("")
        lines.append("This appendix makes the scoring contract explicit. Unless an acceptable variant is listed, the task requires the exact expected answer class shown below.")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Task", "Family", "Ground truth", "Question", "Expected answer summary", "Acceptable variants"),
            rows=self._ground_truth_rows(report),
        )
        lines.append("")
        lines.append("## Task-Level Results")
        lines.append("")
        for item in report.task_level_summaries:
            lines.append(f"### {item.task_id}")
            lines.append("")
            lines.append(f"- Suite: `{item.suite_role.value}`")
            lines.append(f"- Arm: `{item.arm.value}`")
            lines.append(f"- Family: `{item.task_family}`")
            lines.append(f"- Taxonomy: `{item.task_taxonomy.value}`")
            lines.append(f"- Ground truth kind: `{item.ground_truth_kind.value}`")
            lines.append(f"- Run temperature: `{item.run_temperature.value}`")
            lines.append(f"- Repository profile: `{item.repository_profile_label}`")
            lines.append(f"- Status: `{item.status.value}`")
            lines.append(f"- Question: {item.question}")
            lines.append(f"- Repository path: `{item.repository_path}`")
            if item.selector_summary is not None:
                lines.append(f"- Selector: `{item.selector_summary}`")
            lines.append(f"- Correct: `{'yes' if item.status == EvaluationStatus.PASSED else 'no'}`")
            lines.append(f"- Expected answer: {self._format_markdown_value(item.expected_answer)}")
            lines.append(f"- Actual answer: {self._format_markdown_value(item.actual_answer) if item.actual_answer is not None else '-'}")
            lines.append("- Success criteria:")
            for criterion in item.expected_success_criteria:
                lines.append(f"  - {criterion}")
            lines.append(f"- Turns: `{item.turn_count if item.turn_count is not None else '-'}`")
            lines.append(f"- Duration (ms): `{item.duration_ms}`")
            lines.append(f"- Transcript-estimated tokens: `{item.transcript_tokens if item.transcript_tokens is not None else '-'}`")
            lines.append(
                f"- Failure classification: infrastructure=`{self._format_markdown_value(item.is_infrastructure_failure)}`, "
                f"scoring=`{self._format_markdown_value(item.is_scoring_failure)}`, answer=`{self._format_markdown_value(item.is_answer_failure)}`"
            )
            lines.append(f"- Explanation: {item.plain_language_explanation}")
            if item.failure_kind is not None:
                lines.append(f"- Failure kind: `{item.failure_kind.value}`")
            if item.failure_summary is not None:
                lines.append(f"- Failure summary: {item.failure_summary}")
            if item.status == EvaluationStatus.PASSED:
                lines.append("- Answer matched deterministic ground truth.")
            else:
                lines.append("")
                lines.append("| Field | Expected | Actual |")
                lines.append("| --- | --- | --- |")
                if item.field_value_differences:
                    for field_name, values in item.field_value_differences.items():
                        lines.append(
                            f"| {field_name} | {self._format_markdown_value(values.get('expected'))} | "
                            f"{self._format_markdown_value(values.get('actual'))} |"
                        )
                else:
                    lines.append(
                        f"| full_answer | {self._format_markdown_value(item.expected_answer)} | "
                        f"{self._format_markdown_value(item.actual_answer)} |"
                    )
            if item.field_value_differences:
                lines.append("")
            lines.append(f"- Underlying run report: `{item.report_id}`")
            lines.append(f"- Stdout artifact: `{item.stdout_jsonl_path}`")
            lines.append(f"- Rollout artifact: `{item.rollout_artifact_path or '-'}`")
            lines.append(f"- Final answer artifact: `{item.output_last_message_path}`")
            lines.append("")
        lines.append("")
        lines.append("## Chapter 4. Methodology and Reproducibility")
        lines.append("")
        lines.append(
            "This chapter records the deterministic generation inputs, methodological constraints, and artifact paths needed to interpret or reproduce the report."
        )
        lines.append("")
        lines.append("## Methodology")
        lines.append("")
        self._append_markdown_table(
            lines,
            headers=("Field", "Value"),
            rows=tuple(
                (
                    key.replace("_", " ").capitalize(),
                    f"`{value}`" if isinstance(value, (str, int, float, bool)) else self._format_markdown_value(value),
                )
                for key, value in report.methodology.items()
            ),
        )
        lines.append("")
        lines.append("## Threats to Validity")
        lines.append("")
        lines.append("The following constraints limit how far the current results should be generalized:")
        lines.append("")
        for item in report.limitations:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Limitations")
        lines.append("")
        lines.append("- This report freezes the protocol shape for Codex before expanding to additional agents.")
        lines.append("- Stable execution is now A/B, but it remains fixture-backed in this revision for deterministic stability.")
        lines.append("- Passive analytics are supporting evidence and are not used as the primary benchmark source.")
        lines.append("")
        lines.append("## Artifact Map")
        lines.append("")
        lines.append(f"- comparison json: `.suit/evaluation/codex/comparisons/{comparison_dir_name}/comparison.json`")
        lines.append(f"- comparison markdown: `.suit/evaluation/codex/comparisons/{comparison_dir_name}/comparison.md`")
        lines.append(f"- figures directory: `.suit/evaluation/codex/comparisons/{comparison_dir_name}/figures/`")
        lines.append(f"- figure data directory: `.suit/evaluation/codex/comparisons/{comparison_dir_name}/figures/data/`")
        lines.append(f"- stable readonly suitcode run: `{report.stable_readonly_suitcode.report_id}`")
        lines.append(f"- stable readonly baseline run: `{report.stable_readonly_baseline.report_id}`")
        if report.stable_execution_suitcode is not None:
            lines.append(f"- stable execution run: `{report.stable_execution_suitcode.report_id}`")
        if report.stress_readonly_suitcode is not None:
            lines.append(f"- stress readonly suitcode run: `{report.stress_readonly_suitcode.report_id}`")
        if report.stress_readonly_baseline is not None:
            lines.append(f"- stress readonly baseline run: `{report.stress_readonly_baseline.report_id}`")
        if report.calibration_suitcode is not None:
            lines.append(f"- calibration suitcode run: `{report.calibration_suitcode.report_id}`")
        if report.calibration_baseline is not None:
            lines.append(f"- calibration baseline run: `{report.calibration_baseline.report_id}`")
        if report.stable_execution_baseline is not None:
            lines.append(f"- stable execution baseline run: `{report.stable_execution_baseline.report_id}`")
        lines.append("")
        lines.append("## Repro Commands")
        lines.append("")
        for command in report.repro_commands:
            lines.append(f"- `{command}`")
        lines.append("")
        return "\n".join(lines)
