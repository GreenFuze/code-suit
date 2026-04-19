from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from posixpath import dirname
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


@dataclass(frozen=True)
class FilesystemStatSnapshot:
    exists: bool
    is_dir: bool | None
    size: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class ReadOnlyRepositorySnapshot:
    files: dict[str, FilesystemStatSnapshot]
    directories: dict[str, FilesystemStatSnapshot]


@dataclass(frozen=True)
class ReadOnlyRepositoryOpenState:
    workspace: Workspace
    repository: Repository
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


class ReadOnlyRepositoryRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: dict[Path, tuple[Workspace, Repository, ReadOnlyRepositorySnapshot]] = {}

    def open_repository(self, repository_path: str) -> ReadOnlyRepositoryOpenState:
        repository_root = Repository.root_candidate(Path(repository_path))
        with self._lock:
            entry = self._entries.get(repository_root)
            if entry is not None:
                workspace, repository, snapshot = entry
                if self._snapshot_is_clean(repository.root, snapshot):
                    return ReadOnlyRepositoryOpenState(
                        workspace=workspace,
                        repository=repository,
                        reused=True,
                    )
                self._entries.pop(repository_root, None)

            workspace = Workspace(repository_root, materialize_suit_dir=False)
            repository = workspace.repositories[0]
            snapshot = self._capture_snapshot(repository)
            self._entries[repository.root] = (workspace, repository, snapshot)
            return ReadOnlyRepositoryOpenState(
                workspace=workspace,
                repository=repository,
                reused=False,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _capture_snapshot(self, repository: Repository) -> ReadOnlyRepositorySnapshot:
        tracked_files = {
            self._normalize_rel_path(file_info.repository_rel_path)
            for file_info in repository.arch.get_files()
        }
        tracked_directories = {
            self._normalize_rel_path(attachment.attachment_root_rel_path)
            for attachment in repository.provider_attachments
        }
        for file_path in tracked_files:
            tracked_directories.update(self._parent_directories(file_path))
        return ReadOnlyRepositorySnapshot(
            files={
                rel_path: self._stat_snapshot(repository.root / self._to_os_rel_path(rel_path))
                for rel_path in sorted(tracked_files)
            },
            directories={
                rel_path: self._stat_snapshot(repository.root / self._to_os_rel_path(rel_path))
                for rel_path in sorted(tracked_directories)
            },
        )

    def _snapshot_is_clean(self, repository_root: Path, snapshot: ReadOnlyRepositorySnapshot) -> bool:
        try:
            for rel_path, expected in snapshot.files.items():
                current = self._stat_snapshot(repository_root / self._to_os_rel_path(rel_path))
                if current != expected:
                    return False
            for rel_path, expected in snapshot.directories.items():
                current = self._stat_snapshot(repository_root / self._to_os_rel_path(rel_path))
                if current != expected:
                    return False
        except OSError:
            return False
        return True

    @staticmethod
    def _stat_snapshot(path: Path) -> FilesystemStatSnapshot:
        try:
            stat_result = path.stat()
        except OSError:
            return FilesystemStatSnapshot(
                exists=False,
                is_dir=None,
                size=None,
                mtime_ns=None,
            )
        return FilesystemStatSnapshot(
            exists=True,
            is_dir=path.is_dir(),
            size=stat_result.st_size,
            mtime_ns=stat_result.st_mtime_ns,
        )

    @staticmethod
    def _normalize_rel_path(value: str) -> str:
        normalized = value.replace("\\", "/").strip().strip("/")
        return normalized

    @staticmethod
    def _to_os_rel_path(value: str) -> Path:
        if not value:
            return Path(".")
        return Path(*value.split("/"))

    @classmethod
    def _parent_directories(cls, rel_path: str) -> set[str]:
        normalized = cls._normalize_rel_path(rel_path)
        directories = {""}
        parent = dirname(normalized)
        while parent and parent != ".":
            directories.add(parent)
            next_parent = dirname(parent)
            if next_parent == parent:
                break
            parent = next_parent
        return directories
