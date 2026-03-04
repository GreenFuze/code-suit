from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.models import FileInfo
from suitcode.core.repository_models import FileOwnerInfo, OwnedNodeInfo

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class OwnershipIndex:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository
        self._owners = self._build_owner_index()
        self._files_by_path, self._files_by_owner = self._build_file_indexes()

    def owner_for_file(self, repository_rel_path: str) -> FileOwnerInfo:
        try:
            file_info = self._files_by_path[repository_rel_path]
        except KeyError as exc:
            raise ValueError(f"unknown repository file owner for `{repository_rel_path}`") from exc
        return FileOwnerInfo(file_info=file_info, owner=self.owner_info(file_info.owner_id))

    def files_for_owner(self, owner_id: str) -> tuple[FileInfo, ...]:
        self.owner_info(owner_id)
        return self._files_by_owner.get(owner_id, tuple())

    def owner_info(self, owner_id: str) -> OwnedNodeInfo:
        try:
            return self._owners[owner_id]
        except KeyError as exc:
            raise ValueError(f"unknown owner id for repository `{self._repository.root}`: `{owner_id}`") from exc

    def _build_owner_index(self) -> dict[str, OwnedNodeInfo]:
        owners: dict[str, OwnedNodeInfo] = {}
        owner_nodes = (
            *self._repository.arch.get_components(),
            *self._repository.arch.get_aggregators(),
            *self._repository.arch.get_runners(),
            *self._repository.arch.get_package_managers(),
            *self._repository.tests.get_tests(),
        )
        for node in owner_nodes:
            if node.id in owners:
                raise ValueError(f"duplicate owner id detected for repository `{self._repository.root}`: `{node.id}`")
            owners[node.id] = OwnedNodeInfo(id=node.id, kind=node.kind.value, name=node.name)
        return owners

    def _build_file_indexes(self) -> tuple[dict[str, FileInfo], dict[str, tuple[FileInfo, ...]]]:
        files_by_path: dict[str, FileInfo] = {}
        files_by_owner: dict[str, list[FileInfo]] = {}
        for file_info in self._repository.arch.get_files():
            if file_info.owner_id not in self._owners:
                raise ValueError(
                    f"file `{file_info.repository_rel_path}` references unknown owner `{file_info.owner_id}`"
                )
            if file_info.repository_rel_path in files_by_path:
                raise ValueError(f"duplicate file ownership detected for `{file_info.repository_rel_path}`")
            files_by_path[file_info.repository_rel_path] = file_info
            files_by_owner.setdefault(file_info.owner_id, []).append(file_info)
        sorted_files_by_owner = {
            owner_id: tuple(sorted(items, key=lambda item: item.repository_rel_path))
            for owner_id, items in files_by_owner.items()
        }
        return files_by_path, sorted_files_by_owner
