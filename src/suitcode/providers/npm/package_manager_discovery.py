from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm.models import NpmPackageManagerAnalysis


class RepositoryPackageManagerDiscoverer:
    def discover(self, repository_root: Path) -> tuple[NpmPackageManagerAnalysis, ...]:
        root = repository_root.resolve()
        managers = (
            self._manager(
                root,
                node_id="pkgmgr:cargo",
                display_name="cargo",
                manager="cargo",
                config_name="Cargo.toml",
            ),
            self._manager(
                root,
                node_id="pkgmgr:npm:root",
                display_name="npm",
                manager="npm",
                config_name="package.json",
            ),
            self._manager(
                root,
                node_id="pkgmgr:python",
                display_name="python",
                manager="python",
                config_name="pyproject.toml",
            ),
        )
        return tuple(item for item in managers if item.owned_files)

    def _manager(
        self,
        root: Path,
        *,
        node_id: str,
        display_name: str,
        manager: str,
        config_name: str,
    ) -> NpmPackageManagerAnalysis:
        files = sorted(path for path in root.rglob(config_name) if self._is_relevant_config(root, path))
        return NpmPackageManagerAnalysis(
            node_id=node_id,
            display_name=display_name,
            manager=manager,
            config_path=files[0].relative_to(root).as_posix() if files else None,
            owned_files=self._owned_files(root, files),
        )

    @staticmethod
    def _is_relevant_config(root: Path, path: Path) -> bool:
        rel_parts = set(path.relative_to(root).parts[:-1])
        return not rel_parts.intersection({".git", ".suit", "node_modules", "dist", "build", ".next", "__pycache__"})

    @staticmethod
    def _owned_files(root: Path, files: list[Path]) -> tuple[str, ...]:
        return tuple(sorted(path.relative_to(root).as_posix() for path in files if path.exists()))
