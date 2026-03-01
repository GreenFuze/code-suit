from __future__ import annotations

import os
import shutil
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.providers.npm.quality_models import NpmResolvedTool


class NpmQualityToolResolver:
    _SUPPORTED_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})
    _ESLINT_CONFIG_NAMES = (
        "eslint.config.js",
        "eslint.config.cjs",
        "eslint.config.mjs",
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".eslintrc.cjs",
        ".eslintrc.yaml",
        ".eslintrc.yml",
    )
    _PRETTIER_CONFIG_NAMES = (
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.js",
        ".prettierrc.cjs",
        ".prettierrc.mjs",
        "prettier.config.js",
        "prettier.config.cjs",
        "prettier.config.mjs",
    )

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def resolve_linter(self, file_path: Path) -> NpmResolvedTool:
        resolved_file = file_path.expanduser().resolve()
        self._validate_supported_file(resolved_file)
        config_path = self._find_config(resolved_file, self._ESLINT_CONFIG_NAMES)
        if config_path is None:
            raise ValueError(
                f"no supported ESLint config found for `{resolved_file.relative_to(self._repository.root).as_posix()}` "
                f"in repository `{self._repository.root}`"
            )
        executable_path = self._resolve_executable("eslint")
        return NpmResolvedTool(tool="eslint", executable_path=executable_path, config_path=config_path)

    def resolve_formatter(self, file_path: Path) -> NpmResolvedTool:
        resolved_file = file_path.expanduser().resolve()
        self._validate_supported_file(resolved_file)
        config_path = self._find_config(resolved_file, self._PRETTIER_CONFIG_NAMES)
        if config_path is None:
            raise ValueError(
                f"no supported Prettier config found for `{resolved_file.relative_to(self._repository.root).as_posix()}` "
                f"in repository `{self._repository.root}`"
            )
        executable_path = self._resolve_executable("prettier")
        return NpmResolvedTool(tool="prettier", executable_path=executable_path, config_path=config_path)

    def _validate_supported_file(self, file_path: Path) -> None:
        if file_path.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"unsupported npm quality file type `{file_path.suffix}` for `{file_path.relative_to(self._repository.root).as_posix()}`"
            )

    def _find_config(self, file_path: Path, config_names: tuple[str, ...]) -> Path | None:
        current = file_path.parent
        while True:
            for config_name in config_names:
                candidate = current / config_name
                if candidate.exists():
                    return candidate.resolve()
            if current == self._repository.root:
                return None
            current = current.parent

    def _resolve_executable(self, executable_name: str) -> Path:
        local_candidates = self._local_executable_candidates(executable_name)
        for candidate in local_candidates:
            if candidate.exists():
                return candidate.resolve()
        path_candidates = [executable_name]
        if os.name == "nt":
            path_candidates.append(f"{executable_name}.cmd")
        for candidate in path_candidates:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return Path(resolved).resolve()
        raise ValueError(
            f"{executable_name} executable was not found for repository `{self._repository.root}`. "
            f"Install `{executable_name}` or provide it in `node_modules/.bin`."
        )

    def _local_executable_candidates(self, executable_name: str) -> tuple[Path, ...]:
        bin_dir = self._repository.root / "node_modules" / ".bin"
        names = [executable_name]
        if os.name == "nt":
            names.insert(0, f"{executable_name}.cmd")
        return tuple(bin_dir / name for name in names)
