from __future__ import annotations

from suitcode.core.change_models import ChangeTarget
from suitcode.core.intelligence_models import ImpactTarget
from suitcode.mcp.errors import McpNotFoundError, McpValidationError
from suitcode.mcp.models import ChangeImpactView, ComponentContextView, FileContextView, ImpactSummaryView, RepositorySummaryView, SymbolContextView
from suitcode.mcp.presenters import ChangeImpactPresenter, IntelligencePresenter, RepositorySummaryPresenter
from suitcode.mcp.state import WorkspaceRegistry


class ContextMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        intelligence_presenter: IntelligencePresenter,
        repository_summary_presenter: RepositorySummaryPresenter,
        change_impact_presenter: ChangeImpactPresenter,
    ) -> None:
        self._registry = registry
        self._intelligence_presenter = intelligence_presenter
        self._repository_summary_presenter = repository_summary_presenter
        self._change_impact_presenter = change_impact_presenter

    def repository_summary(
        self,
        workspace_id: str,
        repository_id: str,
        preview_limit: int = 10,
    ) -> RepositorySummaryView:
        if preview_limit < 1 or preview_limit > 25:
            raise McpValidationError("preview_limit must be between 1 and 25")
        repository = self._registry.get_repository(workspace_id, repository_id)
        return self._repository_summary_presenter.summary_view(repository, preview_limit)

    def describe_components(
        self,
        workspace_id: str,
        repository_id: str,
        component_ids: tuple[str, ...],
        file_preview_limit: int = 20,
        dependency_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[ComponentContextView, ...]:
        self._validate_exact_batch(component_ids, "component_ids")
        self._validate_preview_limit(file_preview_limit, "file_preview_limit")
        self._validate_preview_limit(dependency_preview_limit, "dependency_preview_limit")
        self._validate_preview_limit(dependent_preview_limit, "dependent_preview_limit")
        self._validate_preview_limit(test_preview_limit, "test_preview_limit")
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            contexts = repository.describe_components(
                component_ids,
                file_preview_limit=file_preview_limit,
                dependency_preview_limit=dependency_preview_limit,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return tuple(self._intelligence_presenter.component_context_view(item) for item in contexts)

    def describe_files(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_paths: tuple[str, ...],
        symbol_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> tuple[FileContextView, ...]:
        self._validate_exact_batch(repository_rel_paths, "repository_rel_paths")
        self._validate_preview_limit(symbol_preview_limit, "symbol_preview_limit")
        self._validate_preview_limit(test_preview_limit, "test_preview_limit")
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            contexts = repository.describe_files(
                repository_rel_paths,
                symbol_preview_limit=symbol_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return tuple(self._intelligence_presenter.file_context_view(item) for item in contexts)

    def describe_symbol_context(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str,
        reference_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> SymbolContextView:
        self._validate_preview_limit(reference_preview_limit, "reference_preview_limit")
        self._validate_preview_limit(test_preview_limit, "test_preview_limit")
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            context = repository.describe_symbol_context(
                symbol_id,
                reference_preview_limit=reference_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        except ValueError as exc:
            raise McpNotFoundError(str(exc)) from exc
        return self._intelligence_presenter.symbol_context_view(context)

    def analyze_impact(
        self,
        workspace_id: str,
        repository_id: str,
        symbol_id: str | None = None,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        reference_preview_limit: int = 20,
        dependent_preview_limit: int = 20,
        test_preview_limit: int = 20,
    ) -> ImpactSummaryView:
        self._validate_preview_limit(reference_preview_limit, "reference_preview_limit")
        self._validate_preview_limit(dependent_preview_limit, "dependent_preview_limit")
        self._validate_preview_limit(test_preview_limit, "test_preview_limit")
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = ImpactTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                owner_id=owner_id,
            )
            summary = repository.analyze_impact(
                target,
                reference_preview_limit=reference_preview_limit,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._intelligence_presenter.impact_summary_view(summary)

    def analyze_change(
        self,
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
        self._validate_change_preview_limit(reference_preview_limit, "reference_preview_limit")
        self._validate_change_preview_limit(dependent_preview_limit, "dependent_preview_limit")
        self._validate_change_preview_limit(test_preview_limit, "test_preview_limit")
        self._validate_change_preview_limit(runner_preview_limit, "runner_preview_limit")
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            target = ChangeTarget(
                symbol_id=symbol_id,
                repository_rel_path=repository_rel_path,
                owner_id=owner_id,
            )
            impact = repository.analyze_change(
                target,
                reference_preview_limit=reference_preview_limit,
                dependent_preview_limit=dependent_preview_limit,
                test_preview_limit=test_preview_limit,
                runner_preview_limit=runner_preview_limit,
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._change_impact_presenter.change_impact_view(impact)

    @staticmethod
    def _validate_exact_batch(items: tuple[str, ...], field_name: str) -> None:
        if not items:
            raise McpValidationError(f"{field_name} must not be empty")
        if len(items) > 25:
            raise McpValidationError(f"{field_name} must not contain more than 25 items")
        if any(not item.strip() for item in items):
            raise McpValidationError(f"{field_name} must not contain empty values")
        if len(set(items)) != len(items):
            raise McpValidationError(f"{field_name} must not contain duplicates")

    @staticmethod
    def _validate_preview_limit(value: int, field_name: str) -> None:
        if value < 1 or value > 50:
            raise McpValidationError(f"{field_name} must be between 1 and 50")

    @staticmethod
    def _validate_change_preview_limit(value: int, field_name: str) -> None:
        if value < 1 or value > 100:
            raise McpValidationError(f"{field_name} must be between 1 and 100")
