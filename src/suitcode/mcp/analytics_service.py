from __future__ import annotations

from pathlib import Path

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.mcp.errors import McpNotFoundError
from suitcode.mcp.models import (
    AnalyticsSummaryView,
    BenchmarkReportView,
    InefficientToolCallView,
    ListResult,
    ToolUsageAnalyticsView,
)
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import AnalyticsPresenter
from suitcode.mcp.state import WorkspaceRegistry


class AnalyticsMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        aggregator: AnalyticsAggregator,
        presenter: AnalyticsPresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._aggregator = aggregator
        self._presenter = presenter

    def get_analytics_summary(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
    ) -> AnalyticsSummaryView:
        repository_root = self._repository_root(workspace_id, repository_id)
        summary = self._aggregator.summary(
            repository_root=repository_root,
            include_global=self._resolve_include_global(include_global, repository_root),
            session_id=self._normalize_session_id(session_id),
        )
        return self._presenter.summary_view(summary)

    def get_tool_usage_analytics(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ToolUsageAnalyticsView]:
        repository_root = self._repository_root(workspace_id, repository_id)
        stats = self._aggregator.tool_usage(
            repository_root=repository_root,
            include_global=self._resolve_include_global(include_global, repository_root),
            session_id=self._normalize_session_id(session_id),
        )
        items = tuple(self._presenter.tool_usage_view(item) for item in stats)
        return self._pagination.paginate(items, limit, offset)

    def get_inefficient_tool_calls(
        self,
        workspace_id: str | None = None,
        repository_id: str | None = None,
        include_global: bool | None = None,
        session_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[InefficientToolCallView]:
        repository_root = self._repository_root(workspace_id, repository_id)
        findings = self._aggregator.inefficient_calls(
            repository_root=repository_root,
            include_global=self._resolve_include_global(include_global, repository_root),
            session_id=self._normalize_session_id(session_id),
        )
        items = tuple(self._presenter.inefficiency_view(item) for item in findings)
        return self._pagination.paginate(items, limit, offset)

    def get_mcp_benchmark_report(self) -> BenchmarkReportView:
        report = self._aggregator.benchmark_report()
        if report is None:
            raise McpNotFoundError("benchmark report not found; run scripts/run_mcp_benchmark.py first")
        return self._presenter.benchmark_report_view(report)

    def _repository_root(self, workspace_id: str | None, repository_id: str | None) -> Path | None:
        if workspace_id is None and repository_id is None:
            return None
        if workspace_id is None or repository_id is None:
            raise ValueError("workspace_id and repository_id must be provided together")
        return self._registry.get_repository(workspace_id, repository_id).root

    @staticmethod
    def _resolve_include_global(include_global: bool | None, repository_root: Path | None) -> bool:
        if include_global is not None:
            return include_global
        return repository_root is None

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str | None:
        if session_id is None:
            return None
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be empty when provided")
        return normalized
