from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace


def _make_supported_npm_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "packages" / "app").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{"name":"repo","private":true,"workspaces":["packages/*"]}\n',
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "package.json").write_text(
        '{"name":"@repo/app","version":"1.0.0"}\n',
        encoding="utf-8",
    )
    return repo_root


def test_workspace_is_logical_container_with_id() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = _make_supported_npm_repo(Path(td) / "repo")

        workspace = Workspace(repo_root)

        assert workspace.id == "workspace:repo"
        assert len(workspace.repositories) == 1
        assert workspace.repository_roots == (repo_root,)


def test_add_repository_returns_repository_instance_and_deduplicates() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = _make_supported_npm_repo(Path(td) / "repo")

        workspace = Workspace(repo_root)
        first = workspace.add_repository(repo_root)
        second = workspace.get_repository(repo_root)

        assert isinstance(first, Repository)
        assert first is second
        assert workspace.repositories == (first,)
        assert workspace.get_repository_by_id(first.id) is first


def test_workspace_adds_multiple_repositories_without_active_repository() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo_one = _make_supported_npm_repo(base / "one")
        repo_two = _make_supported_npm_repo(base / "two")

        workspace = Workspace(repo_one)
        repository_two = workspace.add_repository(repo_two)

        assert workspace.repositories[0].root == repo_one
        assert repository_two.root == repo_two
        assert workspace.repository_roots == (repo_one, repo_two)
        assert workspace.get_repository_by_id("repo:one").root == repo_one
        assert workspace.get_repository_by_id("repo:two").root == repo_two
        assert not hasattr(workspace, "set_active_repository")
        assert not hasattr(workspace, "root")
        assert not hasattr(workspace, "suit_dir")
        assert not hasattr(workspace, "arch")
        assert not hasattr(workspace, "code")
        assert not hasattr(workspace, "tests")
        assert not hasattr(workspace, "quality")


def test_workspace_supported_providers_returns_provider_descriptors() -> None:
    supported = Workspace.supported_providers()

    assert tuple(descriptor.provider_id for descriptor in supported) == ("npm", "python")
    assert supported[0].build_systems == ("npm",)
    assert supported[0].programming_languages == ("javascript", "typescript")
    assert supported[1].build_systems == ("pip",)
    assert supported[1].programming_languages == ("python",)


def test_workspace_construction_fails_for_unsupported_repository() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        with pytest.raises(ValueError, match="unsupported repository"):
            Workspace(repo_root)


def test_workspace_get_repository_by_id_fails_for_unknown_id() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = _make_supported_npm_repo(Path(td) / "repo")

        workspace = Workspace(repo_root)

        with pytest.raises(ValueError, match="unknown repository id"):
            workspace.get_repository_by_id("repo:missing")
