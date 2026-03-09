from __future__ import annotations

from threading import Lock

from suitcode.core.action_models import ActionQuery, ActionTargetKind, RepositoryAction
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.runtime_capability_models import ActionRuntimeCapabilities


class ActionIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository
        self._all_actions_cache: tuple[RepositoryAction, ...] | None = None
        self._all_actions_lock = Lock()

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[ActionProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.providers
            if isinstance(provider, ActionProviderBase)
        )

    def get_actions(self, query: ActionQuery | None = None) -> tuple[RepositoryAction, ...]:
        resolved_query = query or ActionQuery()
        actions = self._all_actions()
        actions = self._filter_by_kind(actions, resolved_query)
        actions = self._filter_by_selector(actions, resolved_query)
        return tuple(
            sorted(
                actions,
                key=lambda item: (
                    item.kind.value,
                    item.target_kind.value,
                    item.target_id,
                    item.provider_id,
                    item.id,
                ),
            )
        )

    def get_runtime_capabilities(self) -> tuple[ActionRuntimeCapabilities, ...]:
        return tuple(provider.get_action_runtime_capabilities() for provider in self.providers)

    def _all_actions(self) -> tuple[RepositoryAction, ...]:
        cached = self._all_actions_cache
        if cached is not None:
            return cached
        with self._all_actions_lock:
            cached = self._all_actions_cache
            if cached is not None:
                return cached
            if not self.providers:
                self._all_actions_cache = tuple()
                return self._all_actions_cache

            by_id: dict[str, RepositoryAction] = {}
            for provider in self.providers:
                provider_id = provider.__class__.descriptor().provider_id
                for action in provider.get_actions():
                    if action.provider_id != provider_id:
                        raise ValueError(
                            f"provider `{provider_id}` returned action `{action.id}` with mismatched provider_id "
                            f"`{action.provider_id}`"
                        )
                    if action.id in by_id:
                        raise ValueError(f"duplicate action id detected across providers: `{action.id}`")
                    by_id[action.id] = action
            self._all_actions_cache = tuple(by_id.values())
            return self._all_actions_cache

    @staticmethod
    def _filter_by_kind(
        actions: tuple[RepositoryAction, ...],
        query: ActionQuery,
    ) -> tuple[RepositoryAction, ...]:
        if not query.action_kinds:
            return actions
        return tuple(action for action in actions if action.kind in query.action_kinds)

    def _filter_by_selector(
        self,
        actions: tuple[RepositoryAction, ...],
        query: ActionQuery,
    ) -> tuple[RepositoryAction, ...]:
        if query.runner_id is not None:
            owner = self._repository.resolve_owner(query.runner_id)
            if owner.kind != "runner":
                raise ValueError(f"owner id is not a runner: `{query.runner_id}`")
            return tuple(
                action
                for action in actions
                if action.target_kind == ActionTargetKind.RUNNER and action.target_id == query.runner_id
            )

        if query.test_id is not None:
            owner = self._repository.resolve_owner(query.test_id)
            if owner.kind != "test_definition":
                raise ValueError(f"owner id is not a test definition: `{query.test_id}`")
            return tuple(
                action
                for action in actions
                if action.target_kind == ActionTargetKind.TEST_DEFINITION and action.target_id == query.test_id
            )

        owner_id: str | None = None
        if query.repository_rel_path is not None:
            owner_id = self._repository.get_file_owner(query.repository_rel_path).owner.id
        elif query.owner_id is not None:
            self._repository.resolve_owner(query.owner_id)
            owner_id = query.owner_id
        elif query.component_id is not None:
            owner = self._repository.resolve_owner(query.component_id)
            if owner.kind != "component":
                raise ValueError(f"owner id is not a component: `{query.component_id}`")
            owner_id = query.component_id

        if owner_id is None:
            return actions
        return tuple(
            action
            for action in actions
            if owner_id in action.owner_ids or (
                action.target_kind == ActionTargetKind.COMPONENT and action.target_id == owner_id
            )
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
