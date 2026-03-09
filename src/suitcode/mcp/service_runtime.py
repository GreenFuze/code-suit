from __future__ import annotations

from dataclasses import dataclass

from suitcode.analytics.aggregation import AnalyticsAggregator
from suitcode.analytics.recorder import ToolCallRecorder
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.mcp.action_service import ActionMcpService
from suitcode.mcp.analytics_service import AnalyticsMcpService
from suitcode.mcp.architecture_service import ArchitectureMcpService
from suitcode.mcp.build_service import BuildMcpService
from suitcode.mcp.code_service import CodeMcpService
from suitcode.mcp.context_service import ContextMcpService
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import (
    ActionPresenter,
    AnalyticsPresenter,
    ArchitecturePresenter,
    BuildPresenter,
    ChangeImpactPresenter,
    CodePresenter,
    IntelligencePresenter,
    OwnershipPresenter,
    ProviderPresenter,
    QualityPresenter,
    RepositoryPresenter,
    RepositorySummaryPresenter,
    RunnerPresenter,
    TestPresenter,
    WorkspacePresenter,
)
from suitcode.mcp.quality_service import QualityMcpService
from suitcode.mcp.runner_service import RunnerMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.mcp.test_service import TestMcpService
from suitcode.mcp.tool_catalog import TOOL_CATALOG
from suitcode.mcp.workspace_service import WorkspaceMcpService


@dataclass(frozen=True)
class McpServiceRuntime:
    provider_presenter: ProviderPresenter
    workspace_presenter: WorkspacePresenter
    repository_presenter: RepositoryPresenter
    architecture_presenter: ArchitecturePresenter
    action_presenter: ActionPresenter
    build_presenter: BuildPresenter
    code_presenter: CodePresenter
    test_presenter: TestPresenter
    runner_presenter: RunnerPresenter
    quality_presenter: QualityPresenter
    ownership_presenter: OwnershipPresenter
    repository_summary_presenter: RepositorySummaryPresenter
    intelligence_presenter: IntelligencePresenter
    change_impact_presenter: ChangeImpactPresenter
    analytics_presenter: AnalyticsPresenter
    analytics_settings: AnalyticsSettings
    analytics_store: JsonlAnalyticsStore
    analytics_recorder: ToolCallRecorder
    analytics_aggregator: AnalyticsAggregator
    workspace_service: WorkspaceMcpService
    architecture_service: ArchitectureMcpService
    action_service: ActionMcpService
    code_service: CodeMcpService
    build_service: BuildMcpService
    test_service: TestMcpService
    quality_service: QualityMcpService
    runner_service: RunnerMcpService
    context_service: ContextMcpService
    analytics_service: AnalyticsMcpService


def build_mcp_service_runtime(
    *,
    registry: WorkspaceRegistry,
    pagination: PaginationPolicy,
) -> McpServiceRuntime:
    provider_presenter = ProviderPresenter()
    workspace_presenter = WorkspacePresenter()
    repository_presenter = RepositoryPresenter()
    architecture_presenter = ArchitecturePresenter()
    action_presenter = ActionPresenter()
    build_presenter = BuildPresenter()
    code_presenter = CodePresenter()
    test_presenter = TestPresenter()
    runner_presenter = RunnerPresenter()
    quality_presenter = QualityPresenter()
    ownership_presenter = OwnershipPresenter()
    repository_summary_presenter = RepositorySummaryPresenter()
    intelligence_presenter = IntelligencePresenter()
    change_impact_presenter = ChangeImpactPresenter()
    analytics_presenter = AnalyticsPresenter()

    analytics_settings = AnalyticsSettings.from_env()
    analytics_store = JsonlAnalyticsStore(analytics_settings)
    analytics_recorder = ToolCallRecorder(analytics_store)
    analytics_aggregator = AnalyticsAggregator(
        analytics_store,
        tool_catalog=tuple(sorted(item.name for item in TOOL_CATALOG)),
        excluded_tools=(
            "get_analytics_summary",
            "get_tool_usage_analytics",
            "get_inefficient_tool_calls",
            "get_mcp_benchmark_report",
        ),
    )

    workspace_service = WorkspaceMcpService(
        registry,
        pagination,
        provider_presenter,
        workspace_presenter,
        repository_presenter,
    )
    architecture_service = ArchitectureMcpService(
        registry,
        pagination,
        architecture_presenter,
        intelligence_presenter,
    )
    action_service = ActionMcpService(
        registry,
        pagination,
        action_presenter,
    )
    code_service = CodeMcpService(
        registry,
        pagination,
        code_presenter,
    )
    build_service = BuildMcpService(
        registry,
        pagination,
        build_presenter,
    )
    test_service = TestMcpService(
        registry,
        pagination,
        test_presenter,
    )
    quality_service = QualityMcpService(
        registry,
        quality_presenter,
    )
    runner_service = RunnerMcpService(
        registry,
        runner_presenter,
    )
    context_service = ContextMcpService(
        registry,
        intelligence_presenter,
        repository_summary_presenter,
        change_impact_presenter,
    )
    analytics_service = AnalyticsMcpService(
        registry,
        pagination,
        analytics_aggregator,
        analytics_presenter,
    )

    return McpServiceRuntime(
        provider_presenter=provider_presenter,
        workspace_presenter=workspace_presenter,
        repository_presenter=repository_presenter,
        architecture_presenter=architecture_presenter,
        action_presenter=action_presenter,
        build_presenter=build_presenter,
        code_presenter=code_presenter,
        test_presenter=test_presenter,
        runner_presenter=runner_presenter,
        quality_presenter=quality_presenter,
        ownership_presenter=ownership_presenter,
        repository_summary_presenter=repository_summary_presenter,
        intelligence_presenter=intelligence_presenter,
        change_impact_presenter=change_impact_presenter,
        analytics_presenter=analytics_presenter,
        analytics_settings=analytics_settings,
        analytics_store=analytics_store,
        analytics_recorder=analytics_recorder,
        analytics_aggregator=analytics_aggregator,
        workspace_service=workspace_service,
        architecture_service=architecture_service,
        action_service=action_service,
        code_service=code_service,
        build_service=build_service,
        test_service=test_service,
        quality_service=quality_service,
        runner_service=runner_service,
        context_service=context_service,
        analytics_service=analytics_service,
    )
