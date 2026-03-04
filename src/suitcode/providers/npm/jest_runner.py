from __future__ import annotations

import subprocess
from pathlib import Path


class JestRunner:
    def __init__(self, repository_root: Path, executable_path: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._executable_path = executable_path.expanduser().resolve()

    def list_test_files(self, package_root: str) -> tuple[str, ...]:
        package_path = (self._repository_root / package_root).resolve()
        completed = subprocess.run(
            [str(self._executable_path), '--listTests'],
            cwd=package_path,
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        if completed.returncode != 0:
            raise ValueError(
                f"jest test listing failed for package `{package_root}` in `{self._repository_root}`: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        files = set()
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            candidate = Path(line)
            if not candidate.is_absolute():
                candidate = (package_path / candidate).resolve()
            if not candidate.exists() or not candidate.is_file():
                raise ValueError(
                    f"jest test listing returned an invalid file path `{line}` for package `{package_root}`"
                )
            files.add(candidate.relative_to(self._repository_root).as_posix())
        return tuple(sorted(files))
