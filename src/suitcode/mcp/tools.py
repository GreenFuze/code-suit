from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS
from suitcode.mcp.models import (
    AddRepositoryResult,
    AggregatorView,
    ActionView,
    CloseWorkspaceResult,
    ComponentView,
    ComponentContextView,
    DependencyRefView,
    ExternalPackageView,
    FileContextView,
    FileView,
    FileOwnerView,
    ImpactSummaryView,
    ListResult,
    LocationView,
    OpenWorkspaceResult,
    PackageManagerView,
    ProviderDescriptorView,
    QualityFileResultView,
    QualityProvidersView,
    ChangeImpactView,
    RelatedTestView,
    RunTestTargetsView,
    RepositorySupportView,
    RepositorySummaryView,
    RepositoryView,
    RunnerView,
    SymbolContextView,
    SymbolView,
    TestDefinitionView,
    TestTargetDescriptionView,
    WorkspaceView,
)
from suitcode.mcp.service import SuitMcpService


def register_tools(app: FastMCP, service: SuitMcpService) -> None:
    @app.tool(name="list_supported_providers", description=TOOL_DESCRIPTIONS["list_supported_providers"], structured_output=True)
    def list_supported_providers(limit: int | None = None, offset: int = 0) -> ListResult[ProviderDescriptorView]:
        return service.list_supported_providers(limit=limit, offset=offset)

    @app.tool(name="inspect_repository_support", description=TOOL_DESCRIPTIONS["inspect_repository_support"], structured_output=True)
    def inspect_repository_support(repository_path: str) -> RepositorySupportView:
        return service.inspect_repository_support(repository_path)

    @app.tool(name="open_workspace", description=TOOL_DESCRIPTIONS["open_workspace"], structured_output=True)
    def open_workspace(repository_path: str) -> OpenWorkspaceResult:
        return service.open_workspace(repository_path)

    @app.tool(name="list_open_workspaces", description=TOOL_DESCRIPTIONS["list_open_workspaces"], structured_output=True)
    def list_open_workspaces(limit: int | None = None, offset: int = 0) -> ListResult[WorkspaceView]:
        return service.list_workspaces(limit=limit, offset=offset)

    @app.tool(name="get_workspace", description=TOOL_DESCRIPTIONS["get_workspace"], structured_output=True)
    def get_workspace(workspace_id: str) -> WorkspaceView:
        return service.get_workspace(workspace_id)

    @app.tool(name="close_workspace", description=TOOL_DESCRIPTIONS["close_workspace"], structured_output=True)
    def close_workspace(workspace_id: str) -> CloseWorkspaceResult:
        service.close_workspace(workspace_id)
        return CloseWorkspaceResult(workspace_id=workspace_id, closed=True)

    @app.tool(name="list_workspace_repositories", description=TOOL_DESCRIPTIONS["list_workspace_repositories"], structured_output=True)
    def list_workspace_repositories(workspace_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RepositoryView]:
        return service.list_workspace_repositories(workspace_id, limit=limit, offset=offset)

    @app.tool(name="get_repository", description=TOOL_DESCRIPTIONS["get_repository"], structured_output=True)
    def get_repository(workspace_id: str, repository_id: str) -> RepositoryView:
        return service.get_repository(workspace_id, repository_id)

    @app.tool(name="get_repository_by_path", description=TOOL_DESCRIPTIONS["get_repository_by_path"], structured_output=True)
    def get_repository_by_path(workspace_id: str, repository_path: str) -> RepositoryView:
        return service.get_repository_by_path(workspace_id, repository_path)

    @app.tool(name="add_repository", description=TOOL_DESCRIPTIONS["add_repository"], structured_output=True)
    def add_repository(workspace_id: str, repository_path: str) -> AddRepositoryResult:
        return service.add_repository(workspace_id, repository_path)

    @app.tool(name="list_components", description=TOOL_DESCRIPTIONS["list_components"], structured_output=True)
    def list_components(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ComponentView]:
        return service.list_components(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_aggregators", description=TOOL_DESCRIPTIONS["list_aggregators"], structured_output=True)
    def list_aggregators(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[AggregatorView]:
        return service.list_aggregators(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_runners", description=TOOL_DESCRIPTIONS["list_runners"], structured_output=True)
    def list_runners(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[RunnerView]:
        return service.list_runners(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_package_managers", description=TOOL_DESCRIPTIONS["list_package_managers"], structured_output=True)
    def list_package_managers(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[PackageManagerView]:
        return service.list_package_managers(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_external_packages", description=TOOL_DESCRIPTIONS["list_external_packages"], structured_output=True)
    def list_external_packages(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[ExternalPackageView]:
        return service.list_external_packages(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_files", description=TOOL_DESCRIPTIONS["list_files"], structured_output=True)
    def list_files(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[FileView]:
        return service.list_files(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="list_actions", description=TOOL_DESCRIPTIONS["list_actions"], structured_output=True)
    def list_actions(
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        component_id: str | None = None,
        runner_id: str | None = None,
        test_id: str | None = None,
        action_kinds: tuple[str, ...] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[ActionView]:
        return service.list_actions(
            workspace_id,
            repository_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            component_id=component_id,
            runner_id=runner_id,
            test_id=test_id,
            action_kinds=action_kinds,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="find_symbols", description=TOOL_DESCRIPTIONS["find_symbols"], structured_output=True)
    def find_symbols(
        workspace_id: str,
        repository_id: str,
        query: str,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
        ) -> ListResult[SymbolView]:
        return service.find_symbols(
            workspace_id,
            repository_id,
            query=query,
            is_case_sensitive=is_case_sensitive,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="list_symbols_in_file", description=TOOL_DESCRIPTIONS["list_symbols_in_file"], structured_output=True)
    def list_symbols_in_file(
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[SymbolView]:
        return service.list_symbols_in_file(
            workspace_id,
            repository_id,
            repository_rel_path,
            query=query,
            is_case_sensitive=is_case_sensitive,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="get_file_owner", description=TOOL_DESCRIPTIONS["get_file_owner"], structured_output=True)
    def get_file_owner(workspace_id: str, repository_id: str, repository_rel_path: str) -> FileOwnerView:
        return service.get_file_owner(workspace_id, repository_id, repository_rel_path)

    @app.tool(name="list_files_by_owner", description=TOOL_DESCRIPTIONS["list_files_by_owner"], structured_output=True)
    def list_files_by_owner(
        workspace_id: str,
        repository_id: str,
        owner_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[FileView]:
        return service.list_files_by_owner(workspace_id, repository_id, owner_id, limit=limit, offset=offset)

    @app.tool(name="find_definition", description=TOOL_DESCRIPTIONS["find_definition"], structured_output=True)
    def find_definition(
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        return service.find_definition(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            line=line,
            column=column,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="find_references", description=TOOL_DESCRIPTIONS["find_references"], structured_output=True)
    def find_references(
        workspace_id: str,
        repository_id: str,
        include_definition: bool = False,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[LocationView]:
        return service.find_references(
            workspace_id,
            repository_id,
            include_definition=include_definition,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            line=line,
            column=column,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="list_tests", description=TOOL_DESCRIPTIONS["list_tests"], structured_output=True)
    def list_tests(workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[TestDefinitionView]:
        return service.list_tests(workspace_id, repository_id, limit=limit, offset=offset)

    @app.tool(name="get_related_tests", description=TOOL_DESCRIPTIONS["get_related_tests"], structured_output=True)
    def get_related_tests(
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[RelatedTestView]:
        return service.get_related_tests(
            workspace_id,
            repository_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            limit=limit,
            offset=offset,
        )

    @app.tool(name="describe_test_target", description=TOOL_DESCRIPTIONS["describe_test_target"], structured_output=True)
    def describe_test_target(workspace_id: str, repository_id: str, test_id: str) -> TestTargetDescriptionView:
        return service.describe_test_target(workspace_id, repository_id, test_id)

    @app.tool(name="run_test_targets", description=TOOL_DESCRIPTIONS["run_test_targets"], structured_output=True)
    def run_test_targets(
        workspace_id: str,
        repository_id: str,
        test_ids: tuple[str, ...],
        timeout_seconds: int = 120,
    ) -> RunTestTargetsView:
        return service.run_test_targets(
            workspace_id,
            repository_id,
            test_ids=test_ids,
            timeout_seconds=timeout_seconds,
        )

    @app.tool(name="list_quality_providers", description=TOOL_DESCRIPTIONS["list_quality_providers"], structured_output=True)
    def list_quality_providers(workspace_id: str, repository_id: str) -> QualityProvidersView:
        return QualityProvidersView(provider_ids=service.list_quality_providers(workspace_id, repository_id))

    @app.tool(name="lint_file", description=TOOL_DESCRIPTIONS["lint_file"], structured_output=True)
    def lint_file(
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str,
        provider_id: str,
        is_fix: bool,
    ) -> QualityFileResultView:
        return service.lint_file(workspace_id, repository_id, repository_rel_path, provider_id, is_fix)

    @app.tool(name="format_file", description=TOOL_DESCRIPTIONS["format_file"], structured_output=True)
    def format_file(
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str,
        provider_id: str,
    ) -> QualityFileResultView:
        return service.format_file(workspace_id, repository_id, repository_rel_path, provider_id)

    @app.tool(name="repository_summary", description=TOOL_DESCRIPTIONS["repository_summary"], structured_output=True)
    def repository_summary(
        workspace_id: str,
        repository_id: str,
        preview_limit: int = 10,
    ) -> RepositorySummaryView:
        return service.repository_summary(workspace_id, repository_id, preview_limit=preview_limit)

    @app.tool(name="describe_components", description=TOOL_DESCRIPTIONS["describe_components"], structured_output=True)
    def describe_components(
        workspace_id: str,
        repository_id: str,
        component_ids: tuple[str, ...],
        file_preview_limit: int = 20,
        dependency_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[ComponentContextView, ...]:
        return service.describe_components(
            workspace_id,
            repository_id,
            component_ids,
            file_preview_limit=file_preview_limit,
            dependency_preview_limit=dependency_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    @app.tool(name="describe_files", description=TOOL_DESCRIPTIONS["describe_files"], structured_output=True)
    def describe_files(
        workspace_id: str,
        repository_id: str,
        repository_rel_paths: tuple[str, ...],
        symbol_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[FileContextView, ...]:
        return service.describe_files(
            workspace_id,
            repository_id,
            repository_rel_paths,
            symbol_preview_limit=symbol_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    @app.tool(name="describe_symbol_context", description=TOOL_DESCRIPTIONS["describe_symbol_context"], structured_output=True)
    def describe_symbol_context(
        workspace_id: str,
        repository_id: str,
        symbol_id: str,
        reference_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> SymbolContextView:
        return service.describe_symbol_context(
            workspace_id,
            repository_id,
            symbol_id,
            reference_preview_limit=reference_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    @app.tool(name="get_component_dependencies", description=TOOL_DESCRIPTIONS["get_component_dependencies"], structured_output=True)
    def get_component_dependencies(
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[DependencyRefView]:
        return service.get_component_dependencies(workspace_id, repository_id, component_id, limit=limit, offset=offset)

    @app.tool(name="get_component_dependents", description=TOOL_DESCRIPTIONS["get_component_dependents"], structured_output=True)
    def get_component_dependents(
        workspace_id: str,
        repository_id: str,
        component_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[str]:
        return service.get_component_dependents(workspace_id, repository_id, component_id, limit=limit, offset=offset)

    @app.tool(name="analyze_impact", description=TOOL_DESCRIPTIONS["analyze_impact"], structured_output=True)
    def analyze_impact(
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        reference_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 20,
    ) -> ImpactSummaryView:
        return service.analyze_impact(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
        )

    @app.tool(name="analyze_change", description=TOOL_DESCRIPTIONS["analyze_change"], structured_output=True)
    def analyze_change(
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        reference_preview_limit: int = 50,
        dependent_preview_limit: int = 50,
        test_preview_limit: int = 25,
        runner_preview_limit: int = 25,
    ) -> ChangeImpactView:
        return service.analyze_change(
            workspace_id,
            repository_id,
            symbol_id=symbol_id,
            repository_rel_path=repository_rel_path,
            owner_id=owner_id,
            reference_preview_limit=reference_preview_limit,
            dependent_preview_limit=dependent_preview_limit,
            test_preview_limit=test_preview_limit,
            runner_preview_limit=runner_preview_limit,
        )
