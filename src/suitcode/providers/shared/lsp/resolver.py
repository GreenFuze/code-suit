from __future__ import annotations

import os
import shutil
from pathlib import Path


class ExecutableResolver:
    def resolve_candidate(
        self,
        explicit_path: str | None,
        local_candidates: tuple[Path, ...],
        path_candidates: tuple[str, ...],
        error_message: str,
    ) -> str:
        if explicit_path is not None:
            explicit = Path(explicit_path).expanduser()
            if explicit.exists():
                return str(explicit.resolve())
            resolved = shutil.which(explicit_path)
            if resolved is not None:
                return resolved
            raise ValueError(error_message)

        for candidate in local_candidates:
            if candidate.exists():
                return str(candidate.resolve())

        for candidate in path_candidates:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved

        raise ValueError(error_message)


class TypeScriptLanguageServerResolver:
    def __init__(self, executable_path: str | None = None, tsserver_path: str | None = None) -> None:
        self._executable_path = executable_path
        self._tsserver_path = tsserver_path
        self._resolver = ExecutableResolver()

    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        root = repository_root.expanduser().resolve()
        language_server = self._resolve_language_server(root)
        tsserver = self._resolve_tsserver(root)
        return (language_server, "--stdio", "--tsserver-path", tsserver)

    def _resolve_language_server(self, repository_root: Path) -> str:
        error_message = (
            "typescript-language-server was not found for repository "
            f"`{repository_root}`. Install `typescript-language-server` and `typescript`, "
            "or configure explicit executable paths."
        )
        return self._resolver.resolve_candidate(
            explicit_path=self._executable_path,
            local_candidates=self._local_language_server_candidates(repository_root),
            path_candidates=("typescript-language-server", "typescript-language-server.cmd"),
            error_message=error_message,
        )

    def _resolve_tsserver(self, repository_root: Path) -> str:
        error_message = (
            "tsserver was not found for repository "
            f"`{repository_root}`. Install `typescript`, or configure an explicit tsserver path."
        )
        return self._resolver.resolve_candidate(
            explicit_path=self._tsserver_path,
            local_candidates=self._local_tsserver_candidates(repository_root),
            path_candidates=("tsserver", "tsserver.cmd"),
            error_message=error_message,
        )

    def _local_language_server_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        bin_dir = repository_root / "node_modules" / ".bin"
        names = ["typescript-language-server"]
        if os.name == "nt":
            names.insert(0, "typescript-language-server.cmd")
        return tuple(bin_dir / name for name in names)

    def _local_tsserver_candidates(self, repository_root: Path) -> tuple[Path, ...]:
        candidates = [repository_root / "node_modules" / "typescript" / "lib" / "tsserver.js"]
        if os.name == "nt":
            candidates.append(repository_root / "node_modules" / ".bin" / "tsserver.cmd")
        candidates.append(repository_root / "node_modules" / ".bin" / "tsserver")
        return tuple(candidates)
