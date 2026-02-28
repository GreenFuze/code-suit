from __future__ import annotations

from pathlib import Path

from suitcode.core.models import ProgrammingLanguage
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)


class OwnedFileInventoryBuilder:
    _OWNER_PRIORITY = {
        "runner": 0,
        "test": 1,
        "package": 2,
        "manager": 3,
    }

    def build(
        self,
        repository_root: Path,
        components: tuple[NpmPackageAnalysis, ...],
        aggregators: tuple[NpmAggregatorAnalysis, ...],
        runners: tuple[NpmRunnerAnalysis, ...],
        tests: tuple[NpmTestAnalysis, ...],
        package_managers: tuple[NpmPackageManagerAnalysis, ...],
    ) -> tuple[NpmOwnedFileAnalysis, ...]:
        assignments: dict[str, tuple[str, int]] = {}

        for runner in runners:
            for referenced_file in runner.referenced_files:
                rel = Path(referenced_file).resolve().relative_to(repository_root).as_posix()
                self._assign(assignments, rel, f"runner:npm:{runner.package_name}:{runner.script_name}", "runner")

        for test in tests:
            for path in test.test_files:
                self._assign(assignments, path, f"test:npm:{test.package_name}", "test")

        for package in components:
            owner_id = f"component:npm:{package.package_name}"
            self._assign(assignments, package.manifest_path, owner_id, "package")
            self._assign_directory_files(assignments, repository_root, package.source_roots, owner_id)
            self._assign_paths(assignments, repository_root, package.artifact_paths, owner_id)

        for aggregator in aggregators:
            owner_id = f"aggregator:npm:{aggregator.package_name}"
            self._assign(assignments, aggregator.manifest_path, owner_id, "package")

        for manager in package_managers:
            for path in manager.owned_files:
                self._assign(assignments, path, manager.node_id, "manager")

        analyses = [
            NpmOwnedFileAnalysis(
                repository_rel_path=path,
                owner_id=owner_id,
                language=self._infer_language(path),
            )
            for path, (owner_id, _) in assignments.items()
        ]
        return tuple(sorted(analyses, key=lambda analysis: analysis.repository_rel_path))

    def _assign_directory_files(self, assignments: dict[str, tuple[str, int]], repository_root: Path, paths: tuple[str, ...], owner_id: str) -> None:
        for relative in paths:
            absolute = repository_root / relative
            if not absolute.exists():
                continue
            if absolute.is_file():
                self._assign(assignments, relative, owner_id, "package")
                continue
            for path in sorted(p for p in absolute.rglob("*") if p.is_file()):
                self._assign(assignments, path.relative_to(repository_root).as_posix(), owner_id, "package")

    def _assign_paths(self, assignments: dict[str, tuple[str, int]], repository_root: Path, paths: tuple[str, ...], owner_id: str) -> None:
        for relative in paths:
            absolute = repository_root / relative
            if not absolute.exists():
                continue
            if absolute.is_file():
                self._assign(assignments, relative, owner_id, "package")
            elif absolute.is_dir():
                for path in sorted(p for p in absolute.rglob("*") if p.is_file()):
                    self._assign(assignments, path.relative_to(repository_root).as_posix(), owner_id, "package")

    def _assign(self, assignments: dict[str, tuple[str, int]], path: str, owner_id: str, owner_kind: str) -> None:
        priority = self._OWNER_PRIORITY[owner_kind]
        current = assignments.get(path)
        if current is None or priority < current[1]:
            assignments[path] = (owner_id, priority)
            return
        if priority == current[1] and current[0] != owner_id:
            raise ValueError(f"ambiguous file ownership for {path}: {current[0]} vs {owner_id}")

    def _infer_language(self, repository_rel_path: str) -> ProgrammingLanguage | None:
        suffix = Path(repository_rel_path).suffix.lower()
        if suffix in {".ts", ".tsx"} or repository_rel_path.endswith(".d.ts"):
            return ProgrammingLanguage.TYPESCRIPT
        if suffix in {".js", ".jsx", ".cjs", ".mjs"}:
            return ProgrammingLanguage.JAVASCRIPT
        if suffix == ".py":
            return ProgrammingLanguage.PYTHON
        if suffix == ".go":
            return ProgrammingLanguage.GO
        if suffix == ".rs":
            return ProgrammingLanguage.RUST
        return None
