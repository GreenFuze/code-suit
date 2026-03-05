from __future__ import annotations

from suitcode.core.action_models import ActionKind, ActionQuery
from suitcode.mcp.errors import McpValidationError
from suitcode.mcp.models import ActionView, ListResult
from suitcode.mcp.pagination import PaginationPolicy
from suitcode.mcp.presenters import ActionPresenter
from suitcode.mcp.state import WorkspaceRegistry


class ActionMcpService:
    def __init__(
        self,
        registry: WorkspaceRegistry,
        pagination: PaginationPolicy,
        action_presenter: ActionPresenter,
    ) -> None:
        self._registry = registry
        self._pagination = pagination
        self._action_presenter = action_presenter

    def list_actions(
        self,
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
        repository = self._registry.get_repository(workspace_id, repository_id)
        try:
            query = ActionQuery(
                repository_rel_path=repository_rel_path,
                owner_id=owner_id,
                component_id=component_id,
                runner_id=runner_id,
                test_id=test_id,
                action_kinds=self._parse_action_kinds(action_kinds),
            )
            actions = repository.list_actions(query)
        except ValueError as exc:
            raise McpValidationError(str(exc)) from exc
        views = tuple(self._action_presenter.action_view(item) for item in actions)
        return self._pagination.paginate(views, limit=limit, offset=offset)

    @staticmethod
    def _parse_action_kinds(action_kinds: tuple[str, ...] | None) -> tuple[ActionKind, ...]:
        if action_kinds is None:
            return tuple()
        parsed: list[ActionKind] = []
        for value in action_kinds:
            normalized = value.strip().lower()
            if not normalized:
                raise ValueError("action_kinds must not contain empty values")
            try:
                parsed.append(ActionKind(normalized))
            except ValueError as exc:
                raise ValueError(f"unsupported action kind: `{value}`") from exc
        if len(set(parsed)) != len(parsed):
            raise ValueError("action_kinds must not contain duplicates")
        return tuple(parsed)
