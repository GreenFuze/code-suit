from __future__ import annotations

import json
import subprocess
from pathlib import Path

from suitcode.evaluation.codex.runner import CodexCliRunner, CodexRunStatus


class _FakeCommandRunner:
    def __init__(self, sessions_root: Path, repository_root: Path) -> None:
        self.commands: list[list[str]] = []
        self._sessions_root = sessions_root
        self._repository_root = repository_root

    def __call__(self, command, *, input, text, capture_output, timeout, check, **kwargs):
        self.commands.append(command)
        output_last_message = Path(command[command.index("--output-last-message") + 1])
        output_last_message.parent.mkdir(parents=True, exist_ok=True)
        output_last_message.write_text('{"workspace_id":"workspace:demo","repository_id":"repo:demo","provider_ids":[],"component_count":0,"test_count":0,"quality_provider_count":0,"overall_truth_availability":"available"}', encoding="utf-8")
        session_path = self._sessions_root / "2026" / "03" / "08" / "run.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            "\n".join(
                (
                    json.dumps({"timestamp": "2026-03-08T10:00:00.000Z", "type": "session_meta", "payload": {"id": "codex-eval-session", "timestamp": "2026-03-08T10:00:00.000Z", "cwd": self._repository_root.as_posix(), "model_provider": "openai"}}),
                    json.dumps({"timestamp": "2026-03-08T10:00:01.000Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run eval"}]}}),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout='{"event":"ok"}\n', stderr="")


def test_runner_executes_codex_and_captures_artifacts(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()
    sessions_root = tmp_path / "sessions"
    command_runner = _FakeCommandRunner(sessions_root, repository_root)
    runner = CodexCliRunner(sessions_root=sessions_root, command_runner=command_runner)

    artifacts = runner.run(
        repository_root=repository_root,
        prompt_text="return json",
        output_schema={"type": "object"},
        output_directory=tmp_path / "run",
        timeout_seconds=30,
        config_overrides=("mcp_servers.suitcode.enabled=false",),
    )

    assert artifacts.status == CodexRunStatus.COMPLETED
    assert artifacts.exit_code == 0
    assert artifacts.stdout_jsonl_path.exists()
    assert artifacts.output_last_message_path.exists()
    assert artifacts.session_artifact_path is not None
    assert artifacts.session_artifact_path.name == "run.jsonl"
    assert not artifacts.session_artifact_ambiguous
    assert "exec" in command_runner.commands[0]
    assert "--json" in command_runner.commands[0]
    assert "--output-schema" in command_runner.commands[0]
    assert "--full-auto" in command_runner.commands[0]
    assert "--config" in command_runner.commands[0]
    assert "mcp_servers.suitcode.enabled=false" in command_runner.commands[0]


def test_runner_returns_cli_error_when_codex_missing(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()

    def _missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    runner = CodexCliRunner(sessions_root=tmp_path / "sessions", command_runner=_missing)
    result = runner.run(
        repository_root=repository_root,
        prompt_text="x",
        output_schema={"type": "object"},
        output_directory=tmp_path / "run",
        timeout_seconds=1,
    )

    assert result.status == CodexRunStatus.CLI_ERROR
    assert result.exit_code is None
    assert "codex executable not found" in (result.failure_summary or "")


def test_runner_returns_timeout_status(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["codex"], timeout=2, output='{"event":"partial"}\n', stderr="still running")

    runner = CodexCliRunner(sessions_root=tmp_path / "sessions", command_runner=_timeout)
    result = runner.run(
        repository_root=repository_root,
        prompt_text="x",
        output_schema={"type": "object"},
        output_directory=tmp_path / "run",
        timeout_seconds=2,
    )

    assert result.status == CodexRunStatus.TIMEOUT
    assert result.exit_code is None
    assert result.stdout_jsonl_path.read_text(encoding="utf-8")
    assert "timed out" in (result.failure_summary or "")
