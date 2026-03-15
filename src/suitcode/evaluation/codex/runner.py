from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Callable

from suitcode.analytics.codex_session_store import CodexSessionStore


class CodexRunStatus(StrEnum):
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    CLI_ERROR = "cli_error"


@dataclass(frozen=True)
class CodexRunArtifacts:
    status: CodexRunStatus
    exit_code: int | None
    duration_ms: int
    command_argv: tuple[str, ...]
    stdout_jsonl_path: Path
    stderr_path: Path
    output_last_message_path: Path
    prompt_path: Path
    schema_path: Path
    session_artifact_path: Path | None
    session_artifact_ambiguous: bool = False
    stderr_excerpt: str | None = None
    failure_summary: str | None = None


class CodexCliRunner:
    def __init__(
        self,
        *,
        codex_binary: str = "codex",
        sessions_root: Path | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._codex_binary = codex_binary
        self._store = CodexSessionStore(sessions_root)
        self._command_runner = command_runner or subprocess.run

    def run(
        self,
        *,
        repository_root: Path,
        prompt_text: str,
        output_schema: dict[str, object],
        output_directory: Path,
        timeout_seconds: int,
        model: str | None = None,
        profile: str | None = None,
        config_overrides: tuple[str, ...] = (),
        full_auto: bool = True,
        sandbox: str = "workspace-write",
        bypass_approvals_and_sandbox: bool = False,
    ) -> CodexRunArtifacts:
        output_directory.mkdir(parents=True, exist_ok=True)
        prompt_path = output_directory / "prompt.txt"
        schema_path = output_directory / "output_schema.json"
        stdout_path = output_directory / "stdout.jsonl"
        stderr_path = output_directory / "stderr.txt"
        last_message_path = output_directory / "last_message.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")
        schema_path.write_text(_json_dump(output_schema), encoding="utf-8")

        before = set(self._store.candidate_sessions())
        command = [
            self._codex_binary,
            "exec",
            "--json",
            "--output-last-message",
            str(last_message_path),
            "--output-schema",
            str(schema_path),
            "--cd",
            str(repository_root),
        ]
        if bypass_approvals_and_sandbox:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        if full_auto:
            command.append("--full-auto")
        else:
            command.extend(["-s", sandbox])
        if model is not None:
            command.extend(["-m", model])
        if profile is not None:
            command.extend(["-p", profile])
        for override in config_overrides:
            command.extend(["--config", override])

        started = perf_counter()
        try:
            completed = self._command_runner(
                command,
                input=prompt_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            duration_ms = int((perf_counter() - started) * 1000)
            stdout_path.write_text("", encoding="utf-8")
            stderr_message = f"codex executable not found: `{self._codex_binary}`"
            stderr_path.write_text(stderr_message, encoding="utf-8")
            return CodexRunArtifacts(
                status=CodexRunStatus.CLI_ERROR,
                exit_code=None,
                duration_ms=duration_ms,
                command_argv=tuple(command),
                stdout_jsonl_path=stdout_path,
                stderr_path=stderr_path,
                output_last_message_path=last_message_path,
                prompt_path=prompt_path,
                schema_path=schema_path,
                session_artifact_path=None,
                stderr_excerpt=stderr_message,
                failure_summary=stderr_message,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((perf_counter() - started) * 1000)
            stdout_value = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr_value = exc.stderr if isinstance(exc.stderr, str) else ""
            stdout_path.write_text(stdout_value, encoding="utf-8")
            stderr_message = stderr_value or f"codex exec timed out after {timeout_seconds} seconds"
            stderr_path.write_text(stderr_message, encoding="utf-8")
            session_artifact_path, ambiguous = self._resolve_session_artifact(repository_root=repository_root, before=before)
            return CodexRunArtifacts(
                status=CodexRunStatus.TIMEOUT,
                exit_code=None,
                duration_ms=duration_ms,
                command_argv=tuple(command),
                stdout_jsonl_path=stdout_path,
                stderr_path=stderr_path,
                output_last_message_path=last_message_path,
                prompt_path=prompt_path,
                schema_path=schema_path,
                session_artifact_path=session_artifact_path,
                session_artifact_ambiguous=ambiguous,
                stderr_excerpt=_excerpt(stderr_message),
                failure_summary=f"codex exec timed out after {timeout_seconds} seconds",
            )

        duration_ms = int((perf_counter() - started) * 1000)
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        session_artifact_path, ambiguous = self._resolve_session_artifact(repository_root=repository_root, before=before)
        failure_summary = None
        if completed.returncode != 0:
            failure_summary = f"codex exec exited with code {completed.returncode}"
        return CodexRunArtifacts(
            status=CodexRunStatus.COMPLETED,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            command_argv=tuple(command),
            stdout_jsonl_path=stdout_path,
            stderr_path=stderr_path,
            output_last_message_path=last_message_path,
            prompt_path=prompt_path,
            schema_path=schema_path,
            session_artifact_path=session_artifact_path,
            session_artifact_ambiguous=ambiguous,
            stderr_excerpt=_excerpt(completed.stderr or ""),
            failure_summary=failure_summary,
        )

    def _resolve_session_artifact(self, *, repository_root: Path, before: set[Path]) -> tuple[Path | None, bool]:
        after = self._store.list_sessions(repository_root=repository_root)
        if not after:
            return None, False
        new_items = [path for path in after if path not in before]
        if len(new_items) == 1:
            return new_items[0], False
        if len(new_items) > 1:
            return new_items[-1], True
        latest = self._store.latest_session(repository_root=repository_root)
        if latest is None:
            return None, False
        return latest, len(after) > 1


def _excerpt(value: str, *, limit: int = 400) -> str | None:
    text = value.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _json_dump(value: dict[str, object]) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)
