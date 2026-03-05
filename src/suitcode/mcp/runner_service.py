from __future__ import annotations

from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import RunnerContextView, RunnerExecutionResultView
from suitcode.mcp.presenters import RunnerPresenter
from suitcode.mcp.state import WorkspaceRegistry


class RunnerMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        runner_presenter: RunnerPresenter,
    ) -> None:
        self._registry = registry
        self._runner_presenter = runner_presenter

    def describe_runner(
        self,
        workspace_id: str,
        repository_id: str,
        runner_id: str,
        file_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> RunnerContextView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            context = repository.describe_runner(
                runner_id,
                file_preview_limit=file_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._runner_presenter.runner_context_view(context)

    def run_runner(
        self,
        workspace_id: str,
        repository_id: str,
        runner_id: str,
        timeout_seconds: int = 300,
    ) -> RunnerExecutionResultView:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            result = repository.run_runner(runner_id, timeout_seconds=timeout_seconds)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._runner_presenter.runner_execution_result_view(result)
