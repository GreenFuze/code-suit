from __future__ import annotations

import os
from pathlib import Path

from suitcode.providers.shared.lsp.resolver import ExecutableResolver


class PythonToolResolver:
    def __init__(self, repository_root: Path, executable_resolver: ExecutableResolver | None = None) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._resolver = executable_resolver or ExecutableResolver()

    def resolve_pytest(self) -> Path:
        return Path(
            self._resolver.resolve_candidate(
                explicit_path=None,
                local_candidates=self._local_pytest_candidates(),
                path_candidates=self._path_pytest_candidates(),
                error_message=(
                    f"pytest was not found for repository `{self._repository_root}`. Install `pytest` in the local virtualenv or on PATH."
                ),
            )
        ).resolve()

    def _local_pytest_candidates(self) -> tuple[Path, ...]:
        root = self._repository_root
        candidates = [
            root / '.venv' / 'bin' / 'pytest',
            root / 'venv' / 'bin' / 'pytest',
            root / '.venv' / 'Scripts' / 'pytest',
            root / 'venv' / 'Scripts' / 'pytest',
            root / '.venv' / 'Scripts' / 'pytest.exe',
            root / 'venv' / 'Scripts' / 'pytest.exe',
            root / '.venv' / 'Scripts' / 'pytest.cmd',
            root / 'venv' / 'Scripts' / 'pytest.cmd',
        ]
        return tuple(candidates)

    def _path_pytest_candidates(self) -> tuple[str, ...]:
        candidates = ['pytest']
        if os.name == 'nt':
            candidates.extend(['pytest.exe', 'pytest.cmd'])
        return tuple(candidates)
