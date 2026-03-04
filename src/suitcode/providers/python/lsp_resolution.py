from __future__ import annotations

import os
from pathlib import Path

from suitcode.providers.shared.lsp.resolver import ExecutableResolver


class BasedPyrightResolver:
    def __init__(self, executable_path: str | None = None) -> None:
        self._executable_path = executable_path
        self._resolver = ExecutableResolver()

    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        root = repository_root.expanduser().resolve()
        executable = self._resolver.resolve_candidate(
            explicit_path=self._executable_path,
            local_candidates=self._local_candidates(root),
            path_candidates=self._path_candidates(),
            error_message=(
                f"basedpyright-langserver was not found for repository `{root}`. "
                'Install `basedpyright`, or configure an explicit executable path.'
            ),
        )
        return (executable, '--stdio')

    def _local_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        candidates = [
            repository_root / '.venv' / 'bin' / 'basedpyright-langserver',
            repository_root / 'venv' / 'bin' / 'basedpyright-langserver',
            repository_root / '.venv' / 'Scripts' / 'basedpyright-langserver',
            repository_root / 'venv' / 'Scripts' / 'basedpyright-langserver',
            repository_root / '.venv' / 'Scripts' / 'basedpyright-langserver.exe',
            repository_root / 'venv' / 'Scripts' / 'basedpyright-langserver.exe',
            repository_root / '.venv' / 'Scripts' / 'basedpyright-langserver.cmd',
            repository_root / 'venv' / 'Scripts' / 'basedpyright-langserver.cmd',
        ]
        if os.name == 'nt':
            candidates.extend(
                [
                    repository_root / '.venv' / 'Scripts' / 'basedpyright-langserver.ps1',
                    repository_root / 'venv' / 'Scripts' / 'basedpyright-langserver.ps1',
                ]
            )
        return tuple(candidates)

    def _path_candidates(self) -> tuple[str, ...]:
        candidates = ['basedpyright-langserver']
        if os.name == 'nt':
            candidates.extend(['basedpyright-langserver.exe', 'basedpyright-langserver.cmd'])
        return tuple(candidates)
