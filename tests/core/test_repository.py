from __future__ import annotations

import tempfile
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_roles import ProviderRole


def _make_supported_npm_repo(repo_root: Path) -> Path:
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "packages" / "app").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        '{"name":"repo","private":true,"workspaces":["packages/*"]}\n',
        encoding="utf-8",
    )
    (repo_root / "packages" / "app" / "package.json").write_text(
        '{"name":"@repo/app","version":"1.0.0","scripts":{"test":"jest"}}\n',
        encoding="utf-8",
    )
    return repo_root


def test_repository_creates_suit_layout_and_back_reference() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = _make_supported_npm_repo(Path(td) / "repo")

        workspace = Workspace(repo_root)
        repository = workspace.repositories[0]

        assert repository.workspace is workspace
        assert repository.root == repo_root
        assert repository.suit_dir == repo_root / ".suit"
        assert (repository.suit_dir / "config.json").exists()
        assert (repository.suit_dir / "state.json").exists()


def test_repository_detects_registered_providers_and_intelligence() -> None:
    with tempfile.TemporaryDirectory() as td:
        repository = Workspace(_make_supported_npm_repo(Path(td) / "repo")).repositories[0]

        assert repository.provider_ids == ("npm",)
        assert repository.provider_roles["npm"] == frozenset(
            {
                ProviderRole.ARCHITECTURE,
                ProviderRole.CODE,
                ProviderRole.TEST,
                ProviderRole.QUALITY,
            }
        )
        assert repository.arch.repository is repository
        assert repository.code.repository is repository
        assert repository.tests.repository is repository
        assert repository.quality.repository is repository


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
        repo_one = _make_supported_npm_repo(base / "one" / "app")
        repo_two = _make_supported_npm_repo(base / "two" / "app")

        workspace = Workspace(repo_one)
        first = workspace.repositories[0]
        second = workspace.add_repository(repo_two)

        assert first.id == "repo:app"
        assert second.id == "repo:app-2"


def test_repository_support_for_path_reports_unsupported_repository() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)

        support = Repository.support_for_path(repo_root)

        assert support.repository_root == repo_root
        assert support.is_supported is False
        assert support.provider_ids == tuple()


def test_repository_construction_fails_when_no_provider_matches() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        (repo_root / ".git").mkdir(parents=True)
        workspace_root = Path(td) / "workspace"
        workspace_root.mkdir(parents=True)
        (workspace_root / "package.json").write_text('{"name":"ws","private":true,"workspaces":["packages/*"]}\n', encoding="utf-8")
        (workspace_root / ".git").mkdir(parents=True)

        workspace = Workspace(workspace_root)

        try:
            workspace.add_repository(repo_root)
        except ValueError as exc:
            assert "unsupported repository" in str(exc)
        else:
            raise AssertionError("expected unsupported repository to fail")
