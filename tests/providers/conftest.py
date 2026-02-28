from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from suitcode.core.repository import Repository
from suitcode.core.workspace import Workspace
from suitcode.providers.npm import NPMProvider


@pytest.fixture
def npm_fixture_root() -> Path:
    return Path("tests/test_repos/npm")


@pytest.fixture
def npm_repo_root(tmp_path: Path, npm_fixture_root: Path) -> Path:
    repo_root = tmp_path / "npm"
    shutil.copytree(npm_fixture_root, repo_root)
    (repo_root / ".git").mkdir()
    return repo_root


@pytest.fixture
def npm_workspace(npm_repo_root: Path) -> Workspace:
    return Workspace(npm_repo_root)


@pytest.fixture
def npm_repository(npm_workspace: Workspace) -> Repository:
    return npm_workspace.repositories[0]


@pytest.fixture
def npm_provider(npm_repository: Repository) -> NPMProvider:
    return NPMProvider(npm_repository)
