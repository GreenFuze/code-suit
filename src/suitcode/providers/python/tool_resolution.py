from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.providers.python.quality_models import PythonResolvedTool
from suitcode.providers.shared.lsp.resolver import ExecutableResolver

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class PythonQualityToolResolver:
    _SUPPORTED_EXTENSIONS = frozenset({'.py'})

    def __init__(self, repository: Repository, executable_path: str | None = None) -> None:
        self._repository = repository
        self._executable_path = executable_path
        self._resolver = ExecutableResolver()

    def resolve(self, file_path: Path) -> PythonResolvedTool:
        resolved_file = file_path.expanduser().resolve()
        if resolved_file.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"unsupported python quality file type `{resolved_file.suffix}` for `{resolved_file.relative_to(self._repository.root).as_posix()}`"
            )
        executable = self._resolver.resolve_candidate(
            explicit_path=self._executable_path,
            local_candidates=self._local_candidates(self._repository.root),
            path_candidates=self._path_candidates(),
            error_message=(
                f"ruff was not found for repository `{self._repository.root}`. Install `ruff` in the local virtualenv or on PATH."
            ),
        )
        return PythonResolvedTool(tool='ruff', executable_path=Path(executable).resolve())

    def _local_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        candidates = [
            repository_root / '.venv' / 'bin' / 'ruff',
            repository_root / 'venv' / 'bin' / 'ruff',
            repository_root / '.venv' / 'Scripts' / 'ruff',
            repository_root / 'venv' / 'Scripts' / 'ruff',
            repository_root / '.venv' / 'Scripts' / 'ruff.exe',
            repository_root / 'venv' / 'Scripts' / 'ruff.exe',
            repository_root / '.venv' / 'Scripts' / 'ruff.cmd',
            repository_root / 'venv' / 'Scripts' / 'ruff.cmd',
        ]
        return tuple(candidates)

    def _path_candidates(self) -> tuple[str, ...]:
        candidates = ['ruff']
        if os.name == 'nt':
            candidates.extend(['ruff.exe', 'ruff.cmd'])
        return tuple(candidates)
