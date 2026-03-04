from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from suitcode.mcp.app import create_mcp_app
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.state import WorkspaceRegistry


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
def service() -> SuitMcpService:
    return SuitMcpService(registry=WorkspaceRegistry())


@pytest.fixture
def opened_workspace(service: SuitMcpService, npm_repo_root: Path):
    return service.open_workspace(str(npm_repo_root))


@pytest.fixture
def app():
    return create_mcp_app()
