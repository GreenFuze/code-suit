from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tomllib
from uuid import uuid4

from suitcode.analytics.codex_analytics_service import CodexAnalyticsService
from suitcode.analytics.codex_session_store import CodexSessionStore
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.evaluation.codex.service import CodexEvaluationService
from suitcode.evaluation.comparison_models import (
    ArmRunReference,
    CodexStandoutComparisonSpec,
    CodexStandoutReport,
    ComparisonDelta,
    EvaluationArm,
    SuiteRole,
)
from suitcode.evaluation.models import CodexEvaluationReport
from suitcode.evaluation.reporting import CodexComparisonReporter


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
        if analytics_service is None:
            settings = AnalyticsSettings.from_env()
            store = CodexSessionStore()
            correlation = AnalyticsCorrelationService(JsonlAnalyticsStore(settings))
            analytics_service = CodexAnalyticsService(
                store,
                correlation_service=correlation,
                capture_builder=CodexTranscriptCaptureBuilder(),
                token_estimator=TranscriptTokenEstimator(),
            )
        self._analytics_service = analytics_service

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

        stable_execution_report: CodexEvaluationReport | None = None
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

        stress_report: CodexEvaluationReport | None = None
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

        passive_summary = None
        if spec.include_passive_usage_summary:
            passive_root = (self._working_directory / spec.passive_repository_root).expanduser().resolve()
            passive_summary = self._analytics_service.repository_summary(passive_root).model_dump(mode="json")

        report = CodexStandoutReport(
            report_id=comparison_id,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            model=model,
            stable_readonly_suitcode=self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STABLE_READONLY, stable_readonly_suitcode),
            stable_readonly_baseline=self._arm_run_reference(EvaluationArm.BASELINE, SuiteRole.STABLE_READONLY, stable_readonly_baseline),
            stable_execution_suitcode=(
                self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STABLE_EXECUTION, stable_execution_report)
                if stable_execution_report is not None
                else None
            ),
            stress_readonly_suitcode=(
                self._arm_run_reference(EvaluationArm.SUITCODE, SuiteRole.STRESS_READONLY, stress_report)
                if stress_report is not None
                else None
            ),
            headline_deltas=self._headline_deltas(stable_readonly_suitcode, stable_readonly_baseline),
            stable_readonly_summary=self._summary_payload(stable_readonly_suitcode),
            stable_execution_summary=(self._summary_payload(stable_execution_report) if stable_execution_report is not None else None),
            stress_summary=(self._summary_payload(stress_report) if stress_report is not None else None),
            passive_usage_summary=passive_summary,
            methodology=self._methodology(
                spec,
                stable_timeout_seconds or spec.stable_timeout_seconds,
                stress_timeout_seconds or spec.stress_timeout_seconds,
                full_auto=readonly_full_auto,
                sandbox=readonly_sandbox,
                bypass_approvals_and_sandbox=readonly_bypass,
            ),
            limitations=self._limitations(),
            repro_commands=self._repro_commands(spec, model=model, profile_suitcode=profile_suitcode, profile_baseline=profile_baseline, skip_execution=skip_execution, skip_stress=skip_stress),
        )
        markdown = self._markdown_report(report)
        self._comparison_reporter.write_report(
            report,
            comparison_markdown=markdown,
            inputs={
                "spec": spec.model_dump(mode="json"),
                "stable_readonly_suitcode_report_id": stable_readonly_suitcode.report_id,
                "stable_readonly_baseline_report_id": stable_readonly_baseline.report_id,
                "stable_execution_report_id": stable_execution_report.report_id if stable_execution_report is not None else None,
                "stress_report_id": stress_report.report_id if stress_report is not None else None,
                "model": model,
                "profile_suitcode": profile_suitcode,
                "profile_baseline": profile_baseline,
            },
        )
        return report

    def load_report(self, report_id: str) -> CodexStandoutReport:
        return self._comparison_reporter.load_report(report_id)

    def load_latest_report(self) -> CodexStandoutReport | None:
        return self._comparison_reporter.load_latest_report()

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

    @staticmethod
    def _ensure_report_usable(report: CodexEvaluationReport, *, suite_label: str) -> None:
        usage_limit_count = report.failure_kind_mix.get("usage_limit", 0)
        if usage_limit_count > 0:
            raise RuntimeError(
                f"Codex usage limit was reached during {suite_label}; standout comparison is not valid until quota resets"
            )

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
        full_auto: bool,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
    ) -> dict[str, object]:
        return {
            "stable_readonly_suite": spec.stable_readonly_tasks_file,
            "stable_execution_suite": spec.stable_execution_tasks_file if spec.include_stable_execution else None,
            "stress_readonly_suite": spec.stress_readonly_tasks_file if spec.include_stress_readonly else None,
            "baseline_isolation": "codex exec with --config mcp_servers.suitcode.enabled=false",
            "codex_execution_mode": ("full_auto" if full_auto else "manual_sandbox"),
            "codex_sandbox": sandbox,
            "codex_bypass_approvals_and_sandbox": bypass_approvals_and_sandbox,
            "headline_comparison": "stable_readonly SuitCode arm vs baseline arm",
            "execution_policy": "stable execution is SuitCode-only in this phase",
            "stress_policy": "stress read-only is SuitCode-only in this phase",
            "token_metric_kind": "transcript_estimated",
            "stable_timeout_seconds": stable_timeout_seconds,
            "stress_timeout_seconds": stress_timeout_seconds,
        }

    @staticmethod
    def _limitations() -> tuple[str, ...]:
        return (
            "Transcript-estimated tokens are not billing-accurate vendor usage.",
            "The headline A/B comparison is limited to the stable read-only suite in this phase.",
            "Stable execution and stress read-only sections are SuitCode-only and are not part of the headline A/B.",
            "Stable suites are fixture-heavy by design; stress suites better reflect live-project complexity.",
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
        return (
            " ".join(parts),
            "python scripts/analyze_codex_comparison.py --latest",
            f"python scripts/run_codex_eval.py --tasks-file {spec.stable_readonly_tasks_file}",
            f"python scripts/run_codex_eval.py --tasks-file {spec.stable_execution_tasks_file}",
            f"python scripts/run_codex_eval.py --tasks-file {spec.stress_readonly_tasks_file}",
        )

    def _markdown_report(self, report: CodexStandoutReport) -> str:
        lines: list[str] = []
        lines.append("# Codex Standout Evaluation")
        lines.append("")
        lines.append(f"- Report id: `{report.report_id}`")
        lines.append(f"- Generated at: `{report.generated_at_utc}`")
        lines.append(f"- Model: `{report.model or 'default'}`")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(
            f"- Stable read-only A/B: SuitCode `{report.stable_readonly_suitcode.task_passed}/{report.stable_readonly_suitcode.task_total}` "
            f"vs baseline `{report.stable_readonly_baseline.task_passed}/{report.stable_readonly_baseline.task_total}`"
        )
        if report.stable_execution_suitcode is not None:
            lines.append(
                f"- Stable execution: SuitCode `{report.stable_execution_suitcode.task_passed}/{report.stable_execution_suitcode.task_total}`"
            )
        if report.stress_readonly_suitcode is not None:
            lines.append(
                f"- Stress read-only: SuitCode `{report.stress_readonly_suitcode.task_passed}/{report.stress_readonly_suitcode.task_total}`"
            )
        lines.append("")
        lines.append("## Stable Read-Only A/B")
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
        if report.stable_execution_summary is not None:
            lines.append("## Stable Execution")
            lines.append("")
            lines.append(f"- Summary: `{json.dumps(report.stable_execution_summary, sort_keys=True)}`")
            lines.append("")
        if report.stress_summary is not None:
            lines.append("## Stress Read-Only")
            lines.append("")
            lines.append(f"- Summary: `{json.dumps(report.stress_summary, sort_keys=True)}`")
            lines.append("")
        if report.passive_usage_summary is not None:
            lines.append("## Passive Codex Usage")
            lines.append("")
            lines.append(f"- Summary: `{json.dumps(report.passive_usage_summary, sort_keys=True)}`")
            lines.append("")
        lines.append("## Methodology")
        lines.append("")
        for key, value in report.methodology.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.append("")
        lines.append("## Limitations")
        lines.append("")
        for item in report.limitations:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("## Repro Commands")
        lines.append("")
        for command in report.repro_commands:
            lines.append(f"- `{command}`")
        lines.append("")
        return "\n".join(lines)
