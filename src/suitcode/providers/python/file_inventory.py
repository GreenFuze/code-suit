from __future__ import annotations

from pathlib import Path

from suitcode.core.models import ProgrammingLanguage
from suitcode.providers.python.models import (
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
)


class PythonOwnedFileInventoryBuilder:
    def build(
        self,
        repository_root: Path,
        components: tuple[PythonPackageComponentAnalysis, ...],
        runners: tuple[PythonRunnerAnalysis, ...],
        package_managers: tuple[PythonPackageManagerAnalysis, ...],
    ) -> tuple[PythonOwnedFileAnalysis, ...]:
        root = repository_root.expanduser().resolve()
        ownership: dict[str, PythonOwnedFileAnalysis] = {}

        for component in components:
            component_root = root / component.package_path
            if not component_root.exists() or not component_root.is_dir():
                continue
            for file_path in sorted(component_root.rglob('*.py')):
                if self._is_ignored(file_path, root):
                    continue
                repository_rel_path = file_path.relative_to(root).as_posix()
                ownership[repository_rel_path] = PythonOwnedFileAnalysis(
                    repository_rel_path=repository_rel_path,
                    owner_id=f'component:python:{component.package_name}',
                    language=ProgrammingLanguage.PYTHON,
                )

        for runner in runners:
            for repository_rel_path in runner.referenced_files:
                ownership[repository_rel_path] = PythonOwnedFileAnalysis(
                    repository_rel_path=repository_rel_path,
                    owner_id=f'runner:python:{runner.script_name}',
                    language=ProgrammingLanguage.PYTHON if repository_rel_path.endswith('.py') else None,
                )

        for manager in package_managers:
            for repository_rel_path in manager.owned_files:
                ownership[repository_rel_path] = PythonOwnedFileAnalysis(
                    repository_rel_path=repository_rel_path,
                    owner_id=manager.node_id,
                    language=ProgrammingLanguage.PYTHON if repository_rel_path.endswith('.py') else None,
                )

        return tuple(ownership[path] for path in sorted(ownership))

    @staticmethod
    def _is_ignored(file_path: Path, repository_root: Path) -> bool:
        relative_parts = file_path.relative_to(repository_root).parts
        return any(
            part in {'__pycache__', '.git', '.venv', 'venv', 'env', '.mypy_cache', '.pytest_cache', 'tests', 'tests_unittest'}
            or part.startswith('.')
            for part in relative_parts[:-1]
        )
