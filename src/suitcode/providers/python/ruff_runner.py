from __future__ import annotations

import json
import subprocess
from pathlib import Path

from suitcode.providers.python.quality_models import (
    PythonFormatRunResult,
    PythonLintRunResult,
    PythonQualityDiagnostic,
    PythonResolvedTool,
)


class RuffRunner:
    def run_check(self, tool: PythonResolvedTool, file_path: Path, is_fix: bool) -> PythonLintRunResult:
        command = [str(tool.executable_path), 'check', '--output-format', 'json']
        if is_fix:
            command.append('--fix')
        command.append(str(file_path))
        result = subprocess.run(command, capture_output=True, text=True, cwd=file_path.parent)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'ruff check failed')
        stdout = result.stdout.strip()
        try:
            payload = json.loads(stdout) if stdout else []
        except json.JSONDecodeError as exc:
            raise ValueError(f'ruff check returned malformed JSON for `{file_path}`') from exc
        diagnostics = tuple(self._to_diagnostic(item) for item in payload)
        return PythonLintRunResult(diagnostics=diagnostics, message=(result.stderr.strip() or None))

    def run_format(self, tool: PythonResolvedTool, file_path: Path) -> PythonFormatRunResult:
        command = [str(tool.executable_path), 'format', str(file_path)]
        result = subprocess.run(command, capture_output=True, text=True, cwd=file_path.parent)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'ruff format failed')
        message = result.stdout.strip() or result.stderr.strip() or None
        return PythonFormatRunResult(message=message)

    def _to_diagnostic(self, payload: object) -> PythonQualityDiagnostic:
        if not isinstance(payload, dict):
            raise ValueError('ruff diagnostic payload must be an object')
        location = payload.get('location') if isinstance(payload.get('location'), dict) else {}
        end_location = payload.get('end_location') if isinstance(payload.get('end_location'), dict) else {}
        return PythonQualityDiagnostic(
            tool='ruff',
            severity='warning',
            message=str(payload.get('message', '')),
            line_start=self._as_int(location.get('row')),
            line_end=self._as_int(end_location.get('row')) or self._as_int(location.get('row')),
            column_start=self._as_int(location.get('column')),
            column_end=self._as_int(end_location.get('column')),
            rule_id=str(payload.get('code')) if payload.get('code') is not None else None,
        )

    def _as_int(self, value: object) -> int | None:
        return value if isinstance(value, int) else None
