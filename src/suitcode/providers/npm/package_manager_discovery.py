from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm.models import NpmPackageManagerAnalysis


class RepositoryPackageManagerDiscoverer:
    def discover(self, repository_root: Path) -> tuple[NpmPackageManagerAnalysis, ...]:
        root = repository_root.resolve()
        analyses = [
            NpmPackageManagerAnalysis(
                node_id="pkgmgr:npm:root",
                display_name="npm",
                manager="npm",
                config_path="package.json",
                owned_files=self._owned_files(root, [(root / "package.json")]),
            )
        ]

        python_files = self._sorted_existing(root, "pyproject.toml") + self._sorted_existing(root, "setup.py")
        if python_files:
            analyses.append(
                NpmPackageManagerAnalysis(
                    node_id="pkgmgr:python",
                    display_name="python",
                    manager="python",
                    config_path=python_files[0].relative_to(root).as_posix(),
                    owned_files=tuple(path.relative_to(root).as_posix() for path in python_files),
                )
            )

        cargo_files = self._sorted_existing(root, "Cargo.toml")
        if cargo_files:
            analyses.append(
                NpmPackageManagerAnalysis(
                    node_id="pkgmgr:cargo",
                    display_name="cargo",
                    manager="cargo",
                    config_path=cargo_files[0].relative_to(root).as_posix(),
                    owned_files=tuple(path.relative_to(root).as_posix() for path in cargo_files),
                )
            )

        go_files = self._sorted_existing(root, "go.mod")
        if go_files:
            analyses.append(
                NpmPackageManagerAnalysis(
                    node_id="pkgmgr:go",
                    display_name="go",
                    manager="go",
                    config_path=go_files[0].relative_to(root).as_posix(),
                    owned_files=tuple(path.relative_to(root).as_posix() for path in go_files),
                )
            )

        return tuple(sorted(analyses, key=lambda analysis: analysis.node_id))

    def _sorted_existing(self, root: Path, pattern: str) -> list[Path]:
        return sorted(path for path in root.rglob(pattern) if path.is_file())

    def _owned_files(self, root: Path, files: list[Path]) -> tuple[str, ...]:
        return tuple(sorted(path.relative_to(root).as_posix() for path in files if path.exists()))
