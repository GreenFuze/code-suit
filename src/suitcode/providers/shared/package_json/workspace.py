from __future__ import annotations

from pathlib import Path

from suitcode.providers.shared.package_json.discoverer import PackageJsonWorkspaceDiscoverer
from suitcode.providers.shared.package_json.loader import PackageJsonLoader
from suitcode.providers.shared.package_json.models import PackageJsonWorkspace


class PackageJsonWorkspaceLoader:
    def __init__(
        self,
        manifest_loader: PackageJsonLoader | None = None,
        discoverer: PackageJsonWorkspaceDiscoverer | None = None,
    ) -> None:
        self._manifest_loader = manifest_loader or PackageJsonLoader()
        self._discoverer = discoverer or PackageJsonWorkspaceDiscoverer(self._manifest_loader)

    def load(self, repository_root: Path) -> PackageJsonWorkspace:
        root = repository_root.expanduser().resolve()
        root_manifest = self._manifest_loader.load(root / "package.json")
        packages = self._discoverer.discover(root, root_manifest)
        return PackageJsonWorkspace(
            repository_root=root,
            root_manifest=root_manifest,
            packages=packages,
        )
