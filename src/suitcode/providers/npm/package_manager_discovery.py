from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm.models import NpmPackageManagerAnalysis


class RepositoryPackageManagerDiscoverer:
    def discover(self, repository_root: Path) -> tuple[NpmPackageManagerAnalysis, ...]:
        root = repository_root.resolve()
        return (
            NpmPackageManagerAnalysis(
                node_id="pkgmgr:npm:root",
                display_name="npm",
                manager="npm",
                config_path="package.json",
                owned_files=self._owned_files(root, [(root / "package.json")]),
            ),
        )

    def _owned_files(self, root: Path, files: list[Path]) -> tuple[str, ...]:
        return tuple(sorted(path.relative_to(root).as_posix() for path in files if path.exists()))
