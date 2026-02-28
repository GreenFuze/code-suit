from __future__ import annotations

from pathlib import Path

from suitcode.providers.shared.package_json.workspace import PackageJsonWorkspaceLoader


FIXTURE_ROOT = Path("tests/test_repos/npm")


def test_package_json_workspace_loader_discovers_all_workspace_packages() -> None:
    workspace = PackageJsonWorkspaceLoader().load(FIXTURE_ROOT)
    assert len(workspace.packages) == 25
    assert "@monorepo/core" in workspace.package_names()
    assert "@monorepo/codegen" in workspace.package_names()
    assert "@monorepo/build-all" in workspace.package_names()
