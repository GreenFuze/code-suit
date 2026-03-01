from __future__ import annotations

import json
import subprocess
from pathlib import Path

from suitcode.core.repository import Repository
from suitcode.providers.npm.quality_models import NpmLintRunResult, NpmQualityDiagnostic, NpmResolvedTool


class EslintRunner:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def run(self, tool: NpmResolvedTool, file_path: Path, is_fix: bool) -> NpmLintRunResult:
        command = [str(tool.executable_path), "--format", "json"]
        if is_fix:
            command.append("--fix")
        command.append(str(file_path))

        completed = subprocess.run(
            command,
            cwd=str(self._repository.root),
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        if completed.returncode not in (0, 1):
            raise RuntimeError(
                f"eslint failed for `{file_path.relative_to(self._repository.root).as_posix()}`: "
                f"{(completed.stderr or stdout).strip()}"
            )
        if not stdout:
            return NpmLintRunResult(diagnostics=tuple(), message=(completed.stderr or "").strip() or None)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"eslint returned malformed JSON for `{file_path.relative_to(self._repository.root).as_posix()}`"
            ) from exc

        diagnostics: list[NpmQualityDiagnostic] = []
        for file_result in payload:
            for message in file_result.get("messages", []):
                diagnostics.append(
                    NpmQualityDiagnostic(
                        tool="eslint",
                        severity=self._severity(message.get("severity")),
                        message=str(message.get("message", "")),
                        line_start=message.get("line"),
                        line_end=message.get("endLine"),
                        column_start=message.get("column"),
                        column_end=message.get("endColumn"),
                        rule_id=message.get("ruleId"),
                    )
                )
        diagnostics.sort(
            key=lambda item: (
                item.severity,
                item.line_start or 0,
                item.column_start or 0,
                item.rule_id or "",
                item.message,
            )
        )
        return NpmLintRunResult(
            diagnostics=tuple(diagnostics),
            message=(completed.stderr or "").strip() or None,
        )

    def _severity(self, value: object) -> str:
        if value == 2:
            return "error"
        if value == 1:
            return "warning"
        return "info"
