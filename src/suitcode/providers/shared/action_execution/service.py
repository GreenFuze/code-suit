from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re

from suitcode.core.validation import validate_timeout_seconds
from suitcode.providers.shared.action_execution.models import ActionExecutionResult, ActionExecutionStatus
from suitcode.providers.shared.action_execution.process import ProcessExecutor


class ActionExecutionService:
    def __init__(
        self,
        repository_root: Path,
        suit_dir: Path,
        process_executor: ProcessExecutor | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._suit_dir = suit_dir.expanduser().resolve()
        self._process_executor = process_executor or ProcessExecutor()

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    def run(
        self,
        *,
        action_id: str,
        command_argv: tuple[str, ...],
        command_cwd: str | None,
        timeout_seconds: int,
        run_group: str,
    ) -> ActionExecutionResult:
        validate_timeout_seconds(timeout_seconds)
        normalized_group = run_group.strip().lower()
        if not normalized_group:
            raise ValueError("run_group must not be empty")
        if re.search(r"[^a-z0-9_-]", normalized_group):
            raise ValueError("run_group must contain only lowercase letters, digits, '-', or '_' characters")

        working_directory = self._resolve_working_directory(command_cwd)
        try:
            execution = self._process_executor.run(
                argv=command_argv,
                cwd=working_directory,
                timeout_seconds=timeout_seconds,
            )
        except OSError as exc:
            argv_display = " ".join(command_argv)
            raise ValueError(f"failed to execute command `{argv_display}`: {exc}") from exc

        log_path = self._write_run_log(action_id, execution.output, normalized_group)
        status = self._resolve_status(execution.exit_code, execution.timed_out)
        return ActionExecutionResult(
            action_id=action_id,
            status=status,
            success=status == ActionExecutionStatus.PASSED,
            command_argv=command_argv,
            command_cwd=command_cwd,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            log_path=log_path,
            output_excerpt=self._excerpt(execution.output),
            output=execution.output,
        )

    def _resolve_working_directory(self, command_cwd: str | None) -> Path:
        if command_cwd is None:
            return self._repository_root
        working_directory = (self._repository_root / command_cwd).resolve()
        try:
            working_directory.relative_to(self._repository_root)
        except ValueError as exc:
            raise ValueError(f"command cwd escapes repository root: `{command_cwd}`") from exc
        if not working_directory.exists() or not working_directory.is_dir():
            raise ValueError(f"command cwd does not exist: `{command_cwd}`")
        return working_directory

    def _write_run_log(self, action_id: str, output: str, run_group: str) -> str:
        runs_dir = (self._suit_dir / "runs" / run_group).resolve()
        runs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_action_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", action_id).strip("._-")
        if not safe_action_id:
            safe_action_id = "action"
        filename = f"{timestamp}-{safe_action_id}.log"
        log_file = runs_dir / filename
        log_file.write_text(output, encoding="utf-8")
        return log_file.relative_to(self._repository_root).as_posix()

    @staticmethod
    def _resolve_status(exit_code: int | None, timed_out: bool) -> ActionExecutionStatus:
        if timed_out:
            return ActionExecutionStatus.TIMEOUT
        if exit_code == 0:
            return ActionExecutionStatus.PASSED
        if exit_code is None:
            return ActionExecutionStatus.ERROR
        return ActionExecutionStatus.FAILED

    @staticmethod
    def _excerpt(output: str, max_lines: int = 40, max_chars: int = 4000) -> str | None:
        stripped = output.strip()
        if not stripped:
            return None
        lines = stripped.splitlines()
        excerpt = "\n".join(lines[-max_lines:])
        if len(excerpt) > max_chars:
            return excerpt[-max_chars:]
        return excerpt
