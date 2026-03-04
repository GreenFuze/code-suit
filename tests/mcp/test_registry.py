from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.mcp.errors import McpNotFoundError
from suitcode.mcp.state import WorkspaceRegistry


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
