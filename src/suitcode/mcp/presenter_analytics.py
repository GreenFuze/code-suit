from __future__ import annotations

from suitcode.analytics.models import AnalyticsSummary, BenchmarkReport, InefficiencyFinding, ToolUsageStats
from suitcode.mcp.models import (
    AnalyticsSummaryView,
    BenchmarkArtifactReferenceView,
    BenchmarkReportView,
    BenchmarkTaskResultView,
    InefficientToolCallView,
    ToolUsageAnalyticsView,
)


class AnalyticsPresenter:
    def __init__(self) -> None:
        from suitcode.mcp.presenter_context import IntelligencePresenter

        self._intelligence_presenter = IntelligencePresenter()

    def summary_view(self, summary: AnalyticsSummary) -> AnalyticsSummaryView:
        return AnalyticsSummaryView(**summary.model_dump())

    def tool_usage_view(self, stats: ToolUsageStats) -> ToolUsageAnalyticsView:
        return ToolUsageAnalyticsView(**stats.model_dump())

    def inefficiency_view(self, finding: InefficiencyFinding) -> InefficientToolCallView:
        return InefficientToolCallView(**finding.model_dump())

    def benchmark_report_view(self, report: BenchmarkReport) -> BenchmarkReportView:
        return BenchmarkReportView(
            schema_version=report.schema_version,
            report_id=report.report_id,
            generated_at_utc=report.generated_at_utc,
            adapter_name=report.adapter_name,
            task_total=report.task_total,
            task_passed=report.task_passed,
            task_failed=report.task_failed,
            task_error=report.task_error,
            avg_tool_calls=report.avg_tool_calls,
            avg_duration_ms=report.avg_duration_ms,
            high_value_tool_usage_rate=report.high_value_tool_usage_rate,
            high_value_tool_early_rate=report.high_value_tool_early_rate,
            deterministic_action_success_rate=report.deterministic_action_success_rate,
            authoritative_provenance_rate=report.authoritative_provenance_rate,
            derived_provenance_rate=report.derived_provenance_rate,
            heuristic_provenance_rate=report.heuristic_provenance_rate,
            truth_coverage=(
                self._intelligence_presenter.truth_coverage_summary_view(report.truth_coverage)
                if report.truth_coverage is not None
                else None
            ),
            tasks=tuple(
                BenchmarkTaskResultView(
                    **{
                        **item.model_dump(exclude={"artifact_references"}),
                        "artifact_references": tuple(
                            BenchmarkArtifactReferenceView(**artifact.model_dump())
                            for artifact in item.artifact_references
                        ),
                    }
                )
                for item in report.tasks
            ),
        )
