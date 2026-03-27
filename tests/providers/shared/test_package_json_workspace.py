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


def test_package_json_workspace_loader_supports_standalone_package_root(tmp_path: Path) -> None:
    package_root = tmp_path / "frontend"
    package_root.mkdir()
    (package_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    workspace = PackageJsonWorkspaceLoader().load(package_root)

    assert workspace.repository_root == package_root.resolve()
    assert len(workspace.packages) == 1
    assert workspace.package_names() == ("frontend",)
    assert workspace.packages[0].package_dir == package_root.resolve()
