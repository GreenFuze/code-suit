from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.models import Component, FileInfo
from suitcode.core.ownership_index import OwnershipIndex

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ComponentContextResolver:
    def __init__(self, repository: Repository, ownership_index: OwnershipIndex) -> None:
        self._repository = repository
        self._ownership_index = ownership_index

    def primary_component_id_for_owner(self, owner_id: str) -> str | None:
        owner = self._ownership_index.owner_info(owner_id)
        if owner.kind == "component":
            return owner.id
        component_ids = {
            self.primary_component_id_for_file(file_info.repository_rel_path, owner.id)
            for file_info in self._ownership_index.files_for_owner(owner_id)
        }
        component_ids.discard(None)
        if not component_ids:
            return None
        if len(component_ids) > 1:
            raise ValueError(f"owner resolves to multiple component contexts: `{owner_id}`")
        return next(iter(component_ids))

    def primary_component_id_for_file(self, repository_rel_path: str, owner_id: str) -> str | None:
        owner = self._ownership_index.owner_info(owner_id)
        if owner.kind == "component":
            return owner.id
        candidates: list[str] = []
        for component in self._repository.arch.get_components():
            component_files = self._ownership_index.files_for_owner(component.id)
            if any(item.repository_rel_path == repository_rel_path for item in component_files):
                candidates.append(component.id)
                continue
            if any(repository_rel_path == root or repository_rel_path.startswith(f"{root}/") for root in component.source_roots):
                candidates.append(component.id)
        candidates = sorted(set(candidates))
        if not candidates:
            return None
        if len(candidates) > 1:
            raise ValueError(f"file resolves to multiple component contexts: `{repository_rel_path}`")
        return candidates[0]

    def related_runner_ids_for_component(self, component: Component, owned_files: tuple[FileInfo, ...]) -> tuple[str, ...]:
        component_paths = {item.repository_rel_path for item in owned_files}
        runner_ids: list[str] = []
        for runner in self._repository.arch.get_runners():
            if runner.cwd and any(path == runner.cwd or path.startswith(f"{runner.cwd}/") for path in component_paths):
                runner_ids.append(runner.id)
                continue
            runner_files = self._ownership_index.files_for_owner(runner.id)
            if any(
                item.repository_rel_path in component_paths
                or item.repository_rel_path == source_root
                or item.repository_rel_path.startswith(f"{source_root}/")
                for item in runner_files
                for source_root in component.source_roots
            ):
                runner_ids.append(runner.id)
        return tuple(sorted(set(runner_ids)))
