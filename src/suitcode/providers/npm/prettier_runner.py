from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.providers.npm.quality_models import NpmFormatRunResult, NpmResolvedTool

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class PrettierRunner:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def run(self, tool: NpmResolvedTool, file_path: Path) -> NpmFormatRunResult:
        completed = subprocess.run(
            [str(tool.executable_path), "--write", str(file_path)],
            cwd=str(self._repository.root),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"prettier failed for `{file_path.relative_to(self._repository.root).as_posix()}`: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )
        output = (completed.stdout or "").strip()
        return NpmFormatRunResult(message=output or None)
