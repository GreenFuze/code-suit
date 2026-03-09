from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.providers.shared.action_execution import (
    ActionExecutionService,
    ActionExecutionStatus,
    ProcessExecutionResult,
)


def test_action_execution_service_writes_logs_and_returns_failed_result(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    suit_dir = repository_root / ".suit"
    suit_dir.mkdir(parents=True)

    class _FakeProcessExecutor:
        def run(self, argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> ProcessExecutionResult:
            assert argv[1:] == ("run", "test")
            assert Path(argv[0]).name.lower().startswith("npm")
            assert cwd == repository_root
            assert timeout_seconds == 30
            return ProcessExecutionResult(
                exit_code=1,
                output="E failed",
                timed_out=False,
                duration_ms=17,
            )

    service = ActionExecutionService(
        repository_root=repository_root,
        suit_dir=suit_dir,
        process_executor=_FakeProcessExecutor(),  # type: ignore[arg-type]
    )

    result = service.run(
        action_id="action:npm:test:@repo/app",
        command_argv=("npm", "run", "test"),
        command_cwd=None,
        timeout_seconds=30,
        run_group="tests",
    )

    assert result.status == ActionExecutionStatus.FAILED
    assert result.success is False
    assert result.duration_ms == 17
    assert result.log_path.startswith(".suit/runs/tests/")
    assert (repository_root / result.log_path).exists()
    assert result.output_excerpt == "E failed"


def test_action_execution_service_marks_timeout_without_exit_code(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    suit_dir = repository_root / ".suit"
    suit_dir.mkdir(parents=True)

    class _TimeoutProcessExecutor:
        def run(self, argv: tuple[str, ...], cwd: Path, timeout_seconds: int) -> ProcessExecutionResult:
            return ProcessExecutionResult(
                exit_code=None,
                output="timeout",
                timed_out=True,
                duration_ms=1000,
            )

    service = ActionExecutionService(
        repository_root=repository_root,
        suit_dir=suit_dir,
        process_executor=_TimeoutProcessExecutor(),  # type: ignore[arg-type]
    )
    result = service.run(
        action_id="action:python:test:pytest",
        command_argv=("pytest",),
        command_cwd=None,
        timeout_seconds=1,
        run_group="tests",
    )

    assert result.status == ActionExecutionStatus.TIMEOUT
    assert result.success is False
    assert result.exit_code is None


def test_action_execution_service_rejects_escape_cwd(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    suit_dir = repository_root / ".suit"
    suit_dir.mkdir(parents=True)

    service = ActionExecutionService(repository_root=repository_root, suit_dir=suit_dir)
    with pytest.raises(ValueError, match="escapes repository root"):
        service.run(
            action_id="action:test",
            command_argv=("python", "-V"),
            command_cwd="../outside",
            timeout_seconds=10,
            run_group="tests",
        )
