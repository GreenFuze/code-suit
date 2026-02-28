from __future__ import annotations

import subprocess
from pathlib import Path

from suitcode.providers.shared.lsp.errors import LspProcessError


class LanguageServerProcess:
    def __init__(self, command: tuple[str, ...], cwd: Path) -> None:
        self._command = command
        self._cwd = cwd
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def stdin(self):
        if self._process is None or self._process.stdin is None:
            raise LspProcessError("language server process has not been started")
        return self._process.stdin

    @property
    def stdout(self):
        if self._process is None or self._process.stdout is None:
            raise LspProcessError("language server process has not been started")
        return self._process.stdout

    def start(self) -> None:
        if self._process is not None:
            return
        try:
            self._process = subprocess.Popen(
                list(self._command),
                cwd=str(self._cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise LspProcessError(f"failed to start language server: {' '.join(self._command)}") from exc

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None

    def __enter__(self) -> "LanguageServerProcess":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
