from __future__ import annotations

from suitcode.providers.python.package_discovery import PythonPackageDiscoverer
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


def test_package_discovery_finds_top_level_packages_only(python_repo_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_repo_root)
    discovered = PythonPackageDiscoverer().discover(python_repo_root, manifest)

    assert tuple(item.package_name for item in discovered) == ('acme',)
    assert discovered[0].package_path == 'src/acme'
