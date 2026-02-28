from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm.package_manager_discovery import RepositoryPackageManagerDiscoverer


FIXTURE_ROOT = Path("tests/test_repos/npm")


def test_package_manager_discovery_finds_multiple_repository_level_managers() -> None:
    managers = RepositoryPackageManagerDiscoverer().discover(FIXTURE_ROOT)
    assert [manager.node_id for manager in managers] == [
        "pkgmgr:cargo",
        "pkgmgr:go",
        "pkgmgr:npm:root",
        "pkgmgr:python",
    ]
