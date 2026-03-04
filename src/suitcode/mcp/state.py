from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.mcp.errors import McpNotFoundError


@dataclass(frozen=True)
class WorkspaceOpenState:
    workspace: Workspace
    repository: Repository
    reused: bool


@dataclass(frozen=True)
class RepositoryAttachState:
    workspace: Workspace
    repository: Repository
    owning_workspace_id: str
    reused: bool


class WorkspaceRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._workspaces_by_id: dict[str, Workspace] = {}
        self._workspace_ids_by_root: dict[Path, str] = {}

    def list_workspaces(self) -> tuple[Workspace, ...]:
        with self._lock:
            return tuple(sorted(self._workspaces_by_id.values(), key=lambda item: item.id))

    def get_workspace(self, workspace_id: str) -> Workspace:
        with self._lock:
            workspace = self._workspaces_by_id.get(workspace_id)
            if workspace is None:
                raise McpNotFoundError(f"unknown workspace id: `{workspace_id}`")
            return workspace

    def get_repository(self, workspace_id: str, repository_id: str) -> Repository:
        workspace = self.get_workspace(workspace_id)
        try:
            return workspace.get_repository_by_id(repository_id)
        except ValueError as exc:
            raise McpNotFoundError(f"unknown repository id `{repository_id}` in workspace `{workspace_id}`") from exc

    def open_workspace(self, repository_path: str) -> WorkspaceOpenState:
        repository_root = Repository.root_candidate(Path(repository_path))
        with self._lock:
            existing_workspace_id = self._workspace_ids_by_root.get(repository_root)
            if existing_workspace_id is not None:
                workspace = self._workspaces_by_id[existing_workspace_id]
                repository = workspace.get_repository(repository_root)
                return WorkspaceOpenState(workspace=workspace, repository=repository, reused=True)

            workspace = Workspace(repository_root)
            self._workspaces_by_id[workspace.id] = workspace
            for repository in workspace.repositories:
                self._workspace_ids_by_root[repository.root] = workspace.id
            return WorkspaceOpenState(workspace=workspace, repository=workspace.repositories[0], reused=False)

    def add_repository(self, workspace_id: str, repository_path: str) -> RepositoryAttachState:
        repository_root = Repository.root_candidate(Path(repository_path))
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            existing_workspace_id = self._workspace_ids_by_root.get(repository_root)
            if existing_workspace_id is not None:
                owning_workspace = self._workspaces_by_id[existing_workspace_id]
                repository = owning_workspace.get_repository(repository_root)
                return RepositoryAttachState(
                    workspace=workspace,
                    repository=repository,
                    owning_workspace_id=existing_workspace_id,
                    reused=True,
                )

            repository = workspace.add_repository(repository_root)
            self._workspace_ids_by_root[repository.root] = workspace.id
            return RepositoryAttachState(
                workspace=workspace,
                repository=repository,
                owning_workspace_id=workspace.id,
                reused=False,
            )

    def close_workspace(self, workspace_id: str) -> None:
        with self._lock:
            workspace = self._workspaces_by_id.pop(workspace_id, None)
            if workspace is None:
                raise McpNotFoundError(f"unknown workspace id: `{workspace_id}`")
            for repository in workspace.repositories:
                self._workspace_ids_by_root.pop(repository.root, None)
