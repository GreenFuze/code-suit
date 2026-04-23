from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from suitcode.analytics.models import StrictModel
from suitcode.analytics.token_economics import TokenEconomicsReport
from suitcode.evaluation.live_study import LiveStudyLaunchManifest
from suitcode.evaluation.models import CodexEvaluationReport


class HybridStudyReport(StrictModel):
    report_id: str
    generated_at: str
    workspace: str
    tracked_repository_label: str | None = None
    live_manifest: LiveStudyLaunchManifest | None = None
    live_sessions: TokenEconomicsReport
    controlled_tasks: CodexEvaluationReport | None = None
    combined_interpretation: tuple[str, ...] = Field(default_factory=tuple)
    paper_readiness_summary: tuple[str, ...] = Field(default_factory=tuple)
    threats_to_validity: tuple[str, ...] = Field(default_factory=tuple)


class HybridStudyArtifactSet(StrictModel):
    report_id: str
    artifact_root: str
    json_path: str
    markdown_path: str


class HybridStudyReporter:
    def build_report(
        self,
        *,
        workspace: Path,
        live_report: TokenEconomicsReport,
        controlled_report: CodexEvaluationReport | None,
        live_manifest: LiveStudyLaunchManifest | None = None,
    ) -> HybridStudyReport:
        workspace_root = workspace.expanduser().resolve()
        combined = self._combined_interpretation(live_report=live_report, controlled_report=controlled_report)
        readiness = self._paper_readiness(live_report=live_report, controlled_report=controlled_report)
        threats = self._threats(live_report=live_report, controlled_report=controlled_report)
        return HybridStudyReport(
            report_id=f"hybrid-study-{uuid4().hex}",
            generated_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            workspace=str(workspace_root),
            tracked_repository_label=(live_manifest.tracked_repository_label if live_manifest is not None else None),
            live_manifest=live_manifest,
            live_sessions=live_report,
            controlled_tasks=controlled_report,
            combined_interpretation=combined,
            paper_readiness_summary=readiness,
            threats_to_validity=threats,
        )

    def write_artifacts(self, *, workspace: Path, report: HybridStudyReport) -> HybridStudyArtifactSet:
        workspace_root = workspace.expanduser().resolve()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        artifact_root = workspace_root / ".suit" / "analytics" / "reports" / f"{timestamp}__{report.report_id}"
        artifact_root.mkdir(parents=True, exist_ok=True)
        json_path = artifact_root / "report.json"
        markdown_path = artifact_root / "report.md"
        json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(self.render_markdown(report), encoding="utf-8")
        return HybridStudyArtifactSet(
            report_id=report.report_id,
            artifact_root=str(artifact_root),
            json_path=str(json_path),
            markdown_path=str(markdown_path),
        )

    def render_markdown(self, report: HybridStudyReport) -> str:
        live = report.live_sessions.total
        controlled = report.controlled_tasks
        lines = [
            "# Hybrid MGA Study Report",
            "",
            "## Experiment Metadata",
            "",
            f"- Report id: `{report.report_id}`",
            f"- Generated at: `{report.generated_at}`",
            f"- Workspace: `{report.workspace}`",
            f"- Tracked repository label: `{report.tracked_repository_label or 'unknown'}`",
            f"- Live analytics runs: `{', '.join(report.live_sessions.matched_analytics_run_ids) if report.live_sessions.matched_analytics_run_ids else 'none'}`",
            f"- Controlled report id: `{controlled.report_id if controlled is not None else 'none'}`",
            "",
            "## Metric Definitions",
            "",
            "- Token-efficiency numbers are estimates, not billing totals and not empirical A/B saved-token claims.",
            "- Live-session estimates come from SuitCode token-economics analytics with transcript correlation when available.",
            "- Controlled-task metrics come from the existing Codex evaluation harness and are reported alongside reliability and latency context.",
            "",
            "## Primary Outcomes",
            "",
            f"- Live response-based estimated reduction: `{_format_pct(live.estimated_task_token_reduction_pct_response_based)}`",
            f"- Live evidence-lower-bound estimated reduction: `{_format_pct(live.estimated_task_token_reduction_pct_evidence_lower_bound)}`",
            f"- Live latency: `avg={live.avg_elapsed_ms:.2f}ms`, `p95={live.p95_elapsed_ms}ms`, `max={live.max_elapsed_ms}ms`",
            f"- Live reliability: `success={live.success_count}`, `failures={live.failure_count}`, `unfinished={live.unfinished_count}`, `interrupted={live.interrupted_count}`",
            f"- Live evidence quality: `authoritative={live.authoritative_evidence_rate:.2f}%`, `derived={live.derived_evidence_rate:.2f}%`, `heuristic={live.heuristic_evidence_rate:.2f}%`",
            (
                f"- Controlled task outcomes: `passed={controlled.task_passed}`, `failed={controlled.task_failed}`, `error={controlled.task_error}`, "
                f"`avg_duration_ms={controlled.avg_duration_ms:.2f}`, `required_tool_success_rate={controlled.required_tool_success_rate:.2%}`"
                if controlled is not None
                else "- Controlled task outcomes: `none`"
            ),
            "",
            "## Guardrails",
            "",
            f"- Live transcript coverage partial: `{live.transcript_coverage_partial}`",
            f"- Live degraded/fallback calls: `{live.degraded_count}` / `{live.fallback_count}`",
            f"- Live retrying calls: `{live.retrying_call_count}`",
            (
                f"- Controlled timeout rate: `{controlled.timeout_rate:.2%}`, retry rate: `{controlled.retry_rate:.2%}`, "
                f"session artifact resolution rate: `{controlled.session_artifact_resolution_rate:.2%}`"
                if controlled is not None
                else "- Controlled timeout/retry guardrails: `none`"
            ),
            "",
            "## Latency Breakdown",
            "",
            "### Live MGA Sessions",
            "",
            *(f"- slow call: `{item.tool_name}` `{item.elapsed_ms}ms` `{item.dominant_stage or 'unknown'}`" for item in report.live_sessions.slowest_calls[:5]),
            "",
            "## Workload-Shape Breakdown",
            "",
            f"- Live by task kind: {', '.join(f'{item.name}={item.event_count}' for item in report.live_sessions.by_task_kind) or 'none'}",
            f"- Live by study kind: {', '.join(f'{item.name}={item.event_count}' for item in report.live_sessions.by_study_kind) or 'none'}",
            (
                f"- Controlled task kind mix: {controlled.task_kind_mix}" if controlled is not None else "- Controlled task kind mix: none"
            ),
            (
                f"- Controlled study kind mix: {controlled.study_kind_mix}" if controlled is not None else "- Controlled study kind mix: none"
            ),
            "",
            "## Live MGA Sessions",
            "",
            *(f"- {line}" for line in report.live_sessions.paper_readiness_summary),
            "",
            "## Controlled MGA Tasks",
            "",
            (
                "\n".join(
                    [
                        f"- tracked repositories: `{', '.join(controlled.tracked_repository_labels) if controlled.tracked_repository_labels else 'none'}`",
                        f"- task total: `{controlled.task_total}`",
                        f"- failure mix: `{controlled.failure_kind_mix}`",
                        f"- correlation quality mix: `{controlled.correlation_quality_mix}`",
                    ]
                )
                if controlled is not None
                else "- No controlled MGA report was included."
            ),
            "",
            "## Combined Interpretation",
            "",
            *(f"- {line}" for line in report.combined_interpretation),
            "",
            "## Paper-Readiness Summary",
            "",
            *(f"- {line}" for line in report.paper_readiness_summary),
            "",
            "## Threats To Validity",
            "",
            *(f"- {line}" for line in report.threats_to_validity),
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _combined_interpretation(
        *,
        live_report: TokenEconomicsReport,
        controlled_report: CodexEvaluationReport | None,
    ) -> tuple[str, ...]:
        lines = [
            "Live MGA analytics now support token-efficiency, latency, reliability, and evidence-quality reporting in one artifact.",
        ]
        if controlled_report is None:
            lines.append("Controlled MGA calibration is not yet attached to this report slice.")
        else:
            lines.append(
                "Controlled MGA tasks provide a bounded complement to live MGA sessions, which reduces over-reliance on opportunistic live-session outcomes."
            )
        if live_report.total.estimated_task_token_reduction_pct_response_based is None:
            lines.append("Transcript-correlated response-based task estimates are still missing for this live slice.")
        return tuple(lines)

    @staticmethod
    def _paper_readiness(
        *,
        live_report: TokenEconomicsReport,
        controlled_report: CodexEvaluationReport | None,
    ) -> tuple[str, ...]:
        total = live_report.total
        supported = "estimated token efficiency with guardrails is supported for live MGA slices"
        if controlled_report is not None and controlled_report.task_passed > 0:
            supported = "hybrid MGA evidence is strong enough for a technical lab report with live and controlled sections"
        blockers: list[str] = []
        if total.estimated_task_token_reduction_pct_response_based is None:
            blockers.append("live transcript-correlated response-based estimates are incomplete")
        if total.interrupted_count > 0 or total.unfinished_count > 0:
            blockers.append("unfinished or interrupted live calls remain")
        if total.p95_elapsed_ms > 120000:
            blockers.append("live semantic latency remains high at the tail")
        if controlled_report is None:
            blockers.append("controlled MGA report is missing")
        elif controlled_report.task_error > 0:
            blockers.append("controlled MGA still has infrastructure/task errors")
        return (
            f"Supported today: {supported}.",
            f"Not yet supported: {'; '.join(blockers) if blockers else 'no major blockers in this slice'}.",
            "Next step: accumulate more clean live MGA runs and at least one stable controlled MGA slice before paper drafting.",
        )

    @staticmethod
    def _threats(
        *,
        live_report: TokenEconomicsReport,
        controlled_report: CodexEvaluationReport | None,
    ) -> tuple[str, ...]:
        notes = [
            "Token estimates remain approximations based on transcript-visible content and deterministic evidence lower bounds.",
            "MGA is the current primary benchmark repository, so external validity is still limited.",
        ]
        if live_report.total.transcript_coverage_partial:
            notes.append("Live transcript correlation is partial for this slice.")
        if controlled_report is None:
            notes.append("No controlled MGA report was attached, so live observations dominate this artifact.")
        return tuple(notes)


def _format_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"
