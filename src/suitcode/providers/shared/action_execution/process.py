from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessExecutionResult:
    exit_code: int | None
    output: str
    timed_out: bool
    duration_ms: int


class ProcessExecutor:
    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        timeout_seconds: int,
    ) -> ProcessExecutionResult:
        if not argv:
            raise ValueError("argv must not be empty")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        start = time.perf_counter()
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            output, _ = process.communicate(timeout=timeout_seconds)
            timed_out = False
            exit_code = process.returncode
        except subprocess.TimeoutExpired as exc:
            process.kill()
            timeout_output, _ = process.communicate()
            output = f"{exc.output or ''}{timeout_output or ''}"
            timed_out = True
            exit_code = None
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ProcessExecutionResult(
            exit_code=exit_code,
            output=output,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )
