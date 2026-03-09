from __future__ import annotations

import subprocess
from pathlib import Path


class PytestRunner:
    _COLLECT_TIMEOUT_SECONDS = 60

    def __init__(self, repository_root: Path, executable_path: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._executable_path = executable_path.expanduser().resolve()

    def collect_test_files(self) -> tuple[str, ...]:
        try:
            completed = subprocess.run(
                [str(self._executable_path), '--collect-only', '-q'],
                cwd=self._repository_root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self._COLLECT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stderr or exc.stdout or '').strip()
            raise ValueError(
                f"pytest collection timed out for repository `{self._repository_root}`"
                f"{': ' + output if output else ''}"
            ) from exc
        if completed.returncode != 0:
            raise ValueError(
                f"pytest collection failed for repository `{self._repository_root}`: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        files = set()
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("=") or " collected in " in line:
                continue
            parts = line.split('::')
            file_candidate = (self._repository_root / parts[0]).resolve()
            if not file_candidate.exists() or not file_candidate.is_file():
                raise ValueError(
                    f"pytest collection returned an invalid file path `{parts[0]}` for repository `{self._repository_root}`"
                )
            files.add(file_candidate.relative_to(self._repository_root).as_posix())
        return tuple(sorted(files))
