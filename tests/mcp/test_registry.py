from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from suitcode.mcp.errors import McpNotFoundError
from suitcode.mcp.state import ReadOnlyRepositoryRegistry, WorkspaceRegistry


def test_registry_open_workspace_reuses_existing_root(service: object, npm_repo_root: Path) -> None:
    registry = WorkspaceRegistry()

    first = registry.open_workspace(str(npm_repo_root))
    second = registry.open_workspace(str(npm_repo_root))

    assert first.workspace.id == second.workspace.id
    assert second.reused is True


def test_registry_add_repository_returns_existing_owner_when_root_already_open(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()

    first_root = tmp_path / "one"
    first_root.mkdir()
    (first_root / ".git").mkdir()
    (first_root / "package.json").write_text('{"name":"root","private":true,"workspaces":["packages/*"]}\n', encoding="utf-8")
    (first_root / "packages").mkdir()
    (first_root / "packages" / "app").mkdir()
    (first_root / "packages" / "app" / "package.json").write_text('{"name":"@root/app"}\n', encoding="utf-8")

    second_root = tmp_path / "two"
    second_root.mkdir()
    (second_root / ".git").mkdir()
    (second_root / "package.json").write_text('{"name":"root2","private":true,"workspaces":["packages/*"]}\n', encoding="utf-8")
    (second_root / "packages").mkdir()
    (second_root / "packages" / "app").mkdir()
    (second_root / "packages" / "app" / "package.json").write_text('{"name":"@root2/app"}\n', encoding="utf-8")

    first_workspace = registry.open_workspace(str(first_root)).workspace
    second_workspace = registry.open_workspace(str(second_root)).workspace

    attached = registry.add_repository(second_workspace.id, str(first_root))

    assert attached.owning_workspace_id == first_workspace.id
    assert attached.reused is True


def test_registry_close_workspace_removes_state(npm_repo_root: Path) -> None:
    registry = WorkspaceRegistry()
    opened = registry.open_workspace(str(npm_repo_root))

    registry.close_workspace(opened.workspace.id)

    with pytest.raises(McpNotFoundError):
        registry.get_workspace(opened.workspace.id)


def test_read_only_registry_reuses_clean_repository_without_materializing_suit(npm_repo_root: Path) -> None:
    registry = ReadOnlyRepositoryRegistry()
    suit_dir = npm_repo_root / ".suit"
    shutil.rmtree(suit_dir, ignore_errors=True)

    first = registry.open_repository(str(npm_repo_root))
    second = registry.open_repository(str(npm_repo_root))

    assert first.reused is False
    assert second.reused is True
    assert first.repository is second.repository
    assert not suit_dir.exists()


def test_read_only_registry_invalidates_on_file_edit(npm_repo_root: Path) -> None:
    registry = ReadOnlyRepositoryRegistry()
    tracked_file = npm_repo_root / "packages" / "core" / "src" / "index.ts"

    first = registry.open_repository(str(npm_repo_root))
    tracked_file.write_text(
        tracked_file.read_text(encoding="utf-8") + "\nexport const registryInvalidation = true;\n",
        encoding="utf-8",
    )
    second = registry.open_repository(str(npm_repo_root))

    assert second.reused is False
    assert first.repository is not second.repository


def test_read_only_registry_invalidates_on_file_creation_in_tracked_directory(npm_repo_root: Path) -> None:
    registry = ReadOnlyRepositoryRegistry()
    created_file = npm_repo_root / "packages" / "core" / "src" / "registry-created.ts"

    first = registry.open_repository(str(npm_repo_root))
    created_file.write_text("export const registryCreated = true;\n", encoding="utf-8")
    second = registry.open_repository(str(npm_repo_root))

    assert second.reused is False
    assert first.repository is not second.repository
