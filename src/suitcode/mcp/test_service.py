from __future__ import annotations

from suitcode.core.tests.models import RelatedTestTarget
from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import ListResult, RelatedTestView, TestDefinitionView
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import TestPresenter
from suitcode.mcp.state import WorkspaceRegistry


class TestMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        test_presenter: TestPresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._test_presenter = test_presenter

    def list_tests(self, workspace_id: str, repository_id: str, limit: int | None = None, offset: int = 0) -> ListResult[TestDefinitionView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        items = tuple(self._test_presenter.test_view(item) for item in repository.tests.get_discovered_tests())
        return self._pagination.paginate(items, limit, offset)

    def get_related_tests(
        self,
        workspace_id: str,
        repository_id: str,
        repository_rel_path: str | None = None,
        owner_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult[RelatedTestView]:
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            items = tuple(
                self._test_presenter.related_test_view(item)
                for item in repository.tests.get_related_tests(
                    RelatedTestTarget(repository_rel_path=repository_rel_path, owner_id=owner_id)
                )
            )
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        return self._pagination.paginate(items, limit, offset)
