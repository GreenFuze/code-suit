from __future__ import annotations

import tempfile
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace


def test_repository_creates_suit_layout_and_back_reference() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        workspace = Workspace(repo_root)
        repository = workspace.repositories[0]

        assert repository.workspace is workspace
        assert repository.root == repo_root
        assert repository.suit_dir == repo_root / ".suit"
        assert (repository.suit_dir / "config.json").exists()
        assert (repository.suit_dir / "state.json").exists()


def test_repository_root_candidate_prefers_vcs_root() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        nested = repo_root / "src" / "pkg"
        (repo_root / ".git").mkdir(parents=True)
        nested.mkdir(parents=True)

        assert Repository.root_candidate(nested) == repo_root


def test_repository_ids_are_collision_safe_with_same_basename() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo_one = base / "one" / "app"
        repo_two = base / "two" / "app"
        (repo_one / ".git").mkdir(parents=True)
        (repo_two / ".git").mkdir(parents=True)

        workspace = Workspace(repo_one)
        first = workspace.repositories[0]
        second = workspace.add_repository(repo_two)

        assert first.id == "repo:app"
        assert second.id == "repo:app-2"
