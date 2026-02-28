from __future__ import annotations

from pathlib import Path

from suitcode.providers.shared.package_json.loader import PackageJsonLoader
from suitcode.providers.shared.package_json.models import PackageJsonManifest, PackageJsonWorkspacePackage


class PackageJsonWorkspaceDiscoverer:
    def __init__(self, loader: PackageJsonLoader | None = None) -> None:
        self._loader = loader or PackageJsonLoader()

    def discover(self, repository_root: Path, root_manifest: PackageJsonManifest) -> tuple[PackageJsonWorkspacePackage, ...]:
        if not root_manifest.workspaces:
            raise ValueError(f"npm workspace root has no 'workspaces': {root_manifest.path}")

        packages_by_path: dict[Path, PackageJsonWorkspacePackage] = {}
        names_by_package: dict[str, Path] = {}
        for workspace_glob in root_manifest.workspaces:
            for directory in sorted(repository_root.glob(workspace_glob)):
                if not directory.is_dir():
                    continue
                manifest_path = directory / "package.json"
                if not manifest_path.exists():
                    continue
                resolved_dir = directory.resolve()
                if resolved_dir in packages_by_path:
                    raise ValueError(f"duplicate workspace package path discovered: {resolved_dir}")
                manifest = self._loader.load(manifest_path)
                if manifest.name is None:
                    raise ValueError(f"workspace package missing name: {manifest_path}")
                if manifest.name in names_by_package:
                    raise ValueError(
                        f"duplicate workspace package name '{manifest.name}': {manifest_path} and {names_by_package[manifest.name]}"
                    )
                names_by_package[manifest.name] = manifest_path
                packages_by_path[resolved_dir] = PackageJsonWorkspacePackage(
                    repository_root=repository_root,
                    package_dir=resolved_dir,
                    manifest=manifest,
                )

        return tuple(packages_by_path[path] for path in sorted(packages_by_path))
