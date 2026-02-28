from __future__ import annotations

import tempfile
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace


def test_workspace_is_logical_container_with_id() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        workspace = Workspace(repo_root)

        assert workspace.id == "workspace:repo"
        assert len(workspace.repositories) == 1
        assert workspace.repository_roots == (repo_root,)


def test_add_repository_returns_repository_instance_and_deduplicates() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        workspace = Workspace(repo_root)
        first = workspace.add_repository(repo_root)
        second = workspace.get_repository(repo_root)

        assert isinstance(first, Repository)
        assert first is second
        assert workspace.repositories == (first,)


def test_workspace_adds_multiple_repositories_without_active_repository() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo_one = base / "one"
        repo_two = base / "two"
        (repo_one / ".git").mkdir(parents=True)
        (repo_two / ".git").mkdir(parents=True)

        workspace = Workspace(repo_one)
        repository_two = workspace.add_repository(repo_two)

        assert workspace.repositories[0].root == repo_one
        assert repository_two.root == repo_two
        assert workspace.repository_roots == (repo_one, repo_two)
        assert not hasattr(workspace, "set_active_repository")
        assert not hasattr(workspace, "root")
        assert not hasattr(workspace, "suit_dir")
