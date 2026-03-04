from __future__ import annotations

import os
from pathlib import Path

from suitcode.providers.shared.lsp.resolver import ExecutableResolver


class NpmTestToolResolver:
    def __init__(self, repository_root: Path, executable_resolver: ExecutableResolver | None = None) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._resolver = executable_resolver or ExecutableResolver()

    def resolve_jest(self) -> Path:
        return Path(
            self._resolver.resolve_candidate(
                explicit_path=None,
                local_candidates=self._local_jest_candidates(),
                path_candidates=self._path_jest_candidates(),
                error_message=(
                    f"jest was not found for repository `{self._repository_root}`. Install `jest` in node_modules or on PATH."
                ),
            )
        ).resolve()

    def _local_jest_candidates(self) -> tuple[Path, ...]:
        bin_dir = self._repository_root / 'node_modules' / '.bin'
        names = ['jest']
        if os.name == 'nt':
            names.insert(0, 'jest.cmd')
            names.append('jest.exe')
        return tuple(bin_dir / name for name in names)

    def _path_jest_candidates(self) -> tuple[str, ...]:
        candidates = ['jest']
        if os.name == 'nt':
            candidates.extend(['jest.cmd', 'jest.exe'])
        return tuple(candidates)
