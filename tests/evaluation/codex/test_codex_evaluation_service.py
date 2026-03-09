from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from suitcode.evaluation.codex.runner import CodexCliRunner
from suitcode.evaluation.codex.service import CodexEvaluationService
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.models import EvaluationFailureKind, EvaluationStatus
from suitcode.evaluation.reporting import CodexEvaluationReporter


class _FakeSuitService:
    def open_workspace(self, repository_path: str):
        return SimpleNamespace(
            workspace=SimpleNamespace(workspace_id="workspace:demo"),
            initial_repository=SimpleNamespace(repository_id="repo:demo"),
        )

    def close_workspace(self, workspace_id: str):
        return None

    def repository_summary(self, workspace_id: str, repository_id: str, preview_limit: int = 8):
        return SimpleNamespace(
            provider_ids=("python",),
            component_count=5,
            test_count=7,
            quality_provider_ids=("ruff",),
        )

    def get_truth_coverage(self, workspace_id: str, repository_id: str):
        return SimpleNamespace(
            overall_availability="available",
            domains=(
                SimpleNamespace(domain="architecture", availability="available", authoritative_count=1, derived_count=0, heuristic_count=0, unavailable_count=0),
                SimpleNamespace(domain="code", availability="available", authoritative_count=1, derived_count=0, heuristic_count=0, unavailable_count=0),
                SimpleNamespace(domain="tests", availability="available", authoritative_count=1, derived_count=0, heuristic_count=0, unavailable_count=0),
                SimpleNamespace(domain="quality", availability="available", authoritative_count=1, derived_count=0, heuristic_count=0, unavailable_count=0),
                SimpleNamespace(domain="actions", availability="available", authoritative_count=1, derived_count=0, heuristic_count=0, unavailable_count=0),
            ),
        )

    def get_minimum_verified_change_set(self, workspace_id: str, repository_id: str, **selector):
        return SimpleNamespace(
            owner=SimpleNamespace(id="component:python:suitcode"),
            primary_component=SimpleNamespace(id="component:python:suitcode"),
            tests=(SimpleNamespace(test_id="test:basic"),),
            build_targets=(SimpleNamespace(action_id="build:pkg"),),
            runner_actions=(),
            quality_validation_operations=(SimpleNamespace(id="quality_op:ruff:lint"),),
            quality_hygiene_operations=(SimpleNamespace(id="quality_op:ruff:format"),),
        )

    def list_build_targets(self, workspace_id: str, repository_id: str, limit: int = 200, offset: int = 0):
        return SimpleNamespace(items=(SimpleNamespace(action_id="build:pkg"),))

    def describe_build_target(self, workspace_id: str, repository_id: str, action_id: str):
        return SimpleNamespace(invocation=SimpleNamespace(argv=("python", "-m", "build")))

    def build_target(self, workspace_id: str, repository_id: str, action_id: str, timeout_seconds: int = 300):
        return SimpleNamespace(success=True)


class _FakeCommandRunner:
    def __init__(self, sessions_root: Path, repository_root: Path) -> None:
        self._sessions_root = sessions_root
        self._repository_root = repository_root

    def __call__(self, command, *, input, text, capture_output, timeout, check, **kwargs):
        output_last_message = Path(command[command.index("--output-last-message") + 1])
        task_id = output_last_message.parent.parent.name
        payload = _TASK_OUTPUTS[task_id]
        output_last_message.parent.mkdir(parents=True, exist_ok=True)
        output_last_message.write_text(json.dumps(payload["answer"]), encoding="utf-8")
        session_path = self._sessions_root / "2026" / "03" / "08" / f"{task_id}.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(_render_session(task_id=task_id, repository_root=self._repository_root), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout='{"event":"ok"}\n', stderr="")


_TASK_OUTPUTS = {
    "orientation-1": {
        "answer": {
            "workspace_id": "workspace:demo",
            "repository_id": "repo:demo",
            "provider_ids": ["python"],
            "component_count": 5,
            "test_count": 7,
            "quality_provider_count": 1,
            "overall_truth_availability": "available",
        },
    },
    "minimum-1": {
        "answer": {
            "owner_id": "component:python:suitcode",
            "primary_component_id": "component:python:suitcode",
            "test_target_ids": ["test:basic"],
            "build_target_ids": ["build:pkg"],
            "runner_action_ids": [],
            "quality_validation_operation_ids": ["quality_op:ruff:lint"],
            "quality_hygiene_operation_ids": ["quality_op:ruff:format"],
        },
    },
    "build-1": {
        "answer": {
            "selected_action_id": "build:pkg",
            "command_preview": ["python", "-m", "build"],
            "execution_status": "passed",
            "succeeded": True,
        },
    },
}


def _render_session(*, task_id: str, repository_root: Path) -> str:
    calls = {
        "orientation-1": [
            ("open_workspace", '{"repository_path":"%s"}' % repository_root.as_posix()),
            ("repository_summary", '{"workspace_id":"workspace:demo","repository_id":"repo:demo","preview_limit":8}'),
            ("get_truth_coverage", '{"workspace_id":"workspace:demo","repository_id":"repo:demo"}'),
        ],
        "minimum-1": [
            ("open_workspace", '{"repository_path":"%s"}' % repository_root.as_posix()),
            ("get_minimum_verified_change_set", '{"workspace_id":"workspace:demo","repository_id":"repo:demo","repository_rel_path":"src/suitcode/mcp/service.py"}'),
        ],
        "build-1": [
            ("open_workspace", '{"repository_path":"%s"}' % repository_root.as_posix()),
            ("list_build_targets", '{"workspace_id":"workspace:demo","repository_id":"repo:demo","limit":200,"offset":0}'),
            ("describe_build_target", '{"workspace_id":"workspace:demo","repository_id":"repo:demo","action_id":"build:pkg"}'),
            ("build_target", '{"workspace_id":"workspace:demo","repository_id":"repo:demo","action_id":"build:pkg","timeout_seconds":120}'),
        ],
    }[task_id]
    lines = [
        json.dumps({"timestamp": "2026-03-08T10:00:00.000Z", "type": "session_meta", "payload": {"id": f"codex-{task_id}", "timestamp": "2026-03-08T10:00:00.000Z", "cwd": repository_root.as_posix(), "model_provider": "openai"}}),
        json.dumps({"timestamp": "2026-03-08T10:00:00.500Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run the task"}]}}),
    ]
    for index, (tool_name, arguments) in enumerate(calls, start=1):
        lines.append(
            json.dumps(
                {
                    "timestamp": f"2026-03-08T10:00:0{index}.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": f"mcp__suitcode__{tool_name}",
                        "arguments": arguments,
                        "call_id": f"call-{index}",
                    },
                }
            )
        )
    lines.append(json.dumps({"timestamp": "2026-03-08T10:00:09.000Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}}))
    return "\n".join(lines)


def test_codex_evaluation_service_runs_tasks_and_writes_report(tmp_path: Path) -> None:
    repository_root = (tmp_path / "repo").resolve()
    repository_root.mkdir()
    sessions_root = tmp_path / "sessions"
    runner = CodexCliRunner(sessions_root=sessions_root, command_runner=_FakeCommandRunner(sessions_root, repository_root))
    reporter = CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs")
    service = CodexEvaluationService(
        working_directory=tmp_path,
        runner=runner,
        reporter=reporter,
        service_factory=_FakeSuitService,
    )
    tasks = (
        CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION, timeout_seconds=120),
        CodexEvaluationTask(
            task_id="minimum-1",
            repository_path="repo",
            task_family=CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET,
            target_selector={"repository_rel_path": "src/suitcode/mcp/service.py"},
            timeout_seconds=120,
        ),
        CodexEvaluationTask(task_id="build-1", repository_path="repo", task_family=CodexTaskFamily.BUILD_EXECUTION, timeout_seconds=120),
    )

    report = service.run(tasks)

    assert report.task_total == 3
    assert report.task_passed == 3
    assert report.task_failed == 0
    assert report.task_error == 0
    assert report.required_tool_success_rate == 1.0
    assert report.answer_schema_success_rate == 1.0
    assert report.avg_transcript_tokens is not None
    assert report.failure_kind_mix == {}
    assert report.retry_rate == 0.0
    latest = service.load_latest_report()
    assert latest is not None
    assert latest.report_id == report.report_id
    assert (reporter.runs_root / report.report_id / "report.json").exists()
    assert (reporter.runs_root / report.report_id / "tasks" / "orientation-1" / "metadata.json").exists()


def test_run_codex_eval_script_reports_summary(monkeypatch, capsys, tmp_path: Path) -> None:
    from scripts import run_codex_eval

    class _FakeEvalService:
        def __init__(self, working_directory: Path | None = None) -> None:
            self._report = None

        def load_tasks(self, tasks_file: Path):
            return (CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION),)

        def run(self, tasks, **kwargs):
            service = CodexEvaluationService(
                working_directory=tmp_path,
                runner=CodexCliRunner(sessions_root=tmp_path / "sessions", command_runner=_FakeCommandRunner(tmp_path / "sessions", (tmp_path / "repo").resolve())),
                reporter=CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs"),
                service_factory=_FakeSuitService,
            )
            (tmp_path / "repo").mkdir(exist_ok=True)
            return service.run(tasks)

    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps([{"task_id": "orientation-1", "repository_path": "repo", "task_family": "orientation"}]), encoding="utf-8")
    monkeypatch.setattr(run_codex_eval, "CodexEvaluationService", _FakeEvalService)
    monkeypatch.setattr(sys, "argv", ["run_codex_eval", "--tasks-file", str(tasks_file)])

    run_codex_eval.main()
    output = capsys.readouterr().out

    assert "Generated Codex evaluation report" in output
    assert "Required-tool success rate" in output


def test_codex_evaluation_service_records_typed_error_result_when_runner_fails(tmp_path: Path) -> None:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()

    class _FailingRunner:
        def run(self, **kwargs):
            raise ValueError("runner timeout")

    reporter = CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs")
    service = CodexEvaluationService(
        working_directory=tmp_path,
        runner=_FailingRunner(),
        reporter=reporter,
        service_factory=_FakeSuitService,
    )

    report = service.run((CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION, timeout_seconds=120),))

    assert report.task_total == 1
    assert report.task_error == 1
    assert report.failure_kind_mix == {EvaluationFailureKind.UNEXPECTED_EXCEPTION.value: 1}
    assert report.tasks[0].status == EvaluationStatus.ERROR
    assert report.tasks[0].failure_kind == EvaluationFailureKind.UNEXPECTED_EXCEPTION
    assert "runner timeout" in (report.tasks[0].failure_summary or "")


def test_codex_evaluation_service_retries_infrastructure_only_failures(tmp_path: Path) -> None:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()

    class _RetryRunner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, **kwargs):
            self.calls += 1
            output_directory = kwargs["output_directory"]
            output_directory.mkdir(parents=True, exist_ok=True)
            stdout_path = output_directory / "stdout.jsonl"
            stderr_path = output_directory / "stderr.txt"
            last_message_path = output_directory / "last_message.txt"
            prompt_path = output_directory / "prompt.txt"
            schema_path = output_directory / "output_schema.json"
            prompt_path.write_text("prompt", encoding="utf-8")
            schema_path.write_text("{}", encoding="utf-8")
            stdout_path.write_text("", encoding="utf-8")
            if self.calls == 1:
                stderr_path.write_text("codex exec exited with code 1", encoding="utf-8")
                last_message_path.write_text("", encoding="utf-8")
                from suitcode.evaluation.codex.runner import CodexRunArtifacts, CodexRunStatus

                return CodexRunArtifacts(
                    status=CodexRunStatus.COMPLETED,
                    exit_code=1,
                    duration_ms=10,
                    stdout_jsonl_path=stdout_path,
                    stderr_path=stderr_path,
                    output_last_message_path=last_message_path,
                    prompt_path=prompt_path,
                    schema_path=schema_path,
                    session_artifact_path=None,
                    stderr_excerpt="codex exec exited with code 1",
                    failure_summary="codex exec exited with code 1",
                )

            payload = _TASK_OUTPUTS["orientation-1"]["answer"]
            last_message_path.write_text(json.dumps(payload), encoding="utf-8")
            session_path = tmp_path / "sessions" / "2026" / "03" / "08" / "retry-orientation.jsonl"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(_render_session(task_id="orientation-1", repository_root=repo), encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            from suitcode.evaluation.codex.runner import CodexRunArtifacts, CodexRunStatus

            return CodexRunArtifacts(
                status=CodexRunStatus.COMPLETED,
                exit_code=0,
                duration_ms=12,
                stdout_jsonl_path=stdout_path,
                stderr_path=stderr_path,
                output_last_message_path=last_message_path,
                prompt_path=prompt_path,
                schema_path=schema_path,
                session_artifact_path=session_path,
            )

    reporter = CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs")
    service = CodexEvaluationService(
        working_directory=tmp_path,
        runner=_RetryRunner(),
        reporter=reporter,
        service_factory=_FakeSuitService,
    )

    report = service.run((CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION, timeout_seconds=120),))

    assert report.task_passed == 1
    assert report.retry_rate == 1.0
    assert report.retried_task_count == 1
    assert report.post_retry_pass_count == 1
    assert report.tasks[0].attempt_count == 2
    assert report.tasks[0].infrastructure_retry_applied is True
    assert report.tasks[0].attempt_failure_kinds == (EvaluationFailureKind.CLI_ERROR.value,)
    assert len(report.tasks[0].required_tool_traces) == 6


def test_codex_evaluation_service_classifies_usage_limit_without_retry(tmp_path: Path) -> None:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()

    class _UsageLimitRunner:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, **kwargs):
            self.calls += 1
            output_directory = kwargs["output_directory"]
            output_directory.mkdir(parents=True, exist_ok=True)
            stdout_path = output_directory / "stdout.jsonl"
            stderr_path = output_directory / "stderr.txt"
            last_message_path = output_directory / "last_message.txt"
            prompt_path = output_directory / "prompt.txt"
            schema_path = output_directory / "output_schema.json"
            prompt_path.write_text("prompt", encoding="utf-8")
            schema_path.write_text("{}", encoding="utf-8")
            stdout_path.write_text("{\"type\":\"error\",\"message\":\"You've hit your usage limit.\"}\n", encoding="utf-8")
            stderr_path.write_text("Reading prompt from stdin...", encoding="utf-8")
            last_message_path.write_text("", encoding="utf-8")
            session_path = tmp_path / "sessions" / "2026" / "03" / "08" / "usage-limit.jsonl"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(
                _render_session(task_id="orientation-1", repository_root=repo)
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-03-08T10:00:10.000Z",
                        "type": "event_msg",
                        "payload": {"type": "token_count", "rate_limits": {"credits": {"has_credits": False}}},
                    }
                ),
                encoding="utf-8",
            )
            from suitcode.evaluation.codex.runner import CodexRunArtifacts, CodexRunStatus

            return CodexRunArtifacts(
                status=CodexRunStatus.COMPLETED,
                exit_code=1,
                duration_ms=10,
                stdout_jsonl_path=stdout_path,
                stderr_path=stderr_path,
                output_last_message_path=last_message_path,
                prompt_path=prompt_path,
                schema_path=schema_path,
                session_artifact_path=session_path,
                stderr_excerpt="Reading prompt from stdin...",
                failure_summary="codex exec exited with code 1",
            )

    reporter = CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs")
    service = CodexEvaluationService(
        working_directory=tmp_path,
        runner=_UsageLimitRunner(),
        reporter=reporter,
        service_factory=_FakeSuitService,
    )

    report = service.run((CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION, timeout_seconds=120),))

    assert report.task_error == 1
    assert report.retry_rate == 0.0
    assert report.failure_kind_mix == {EvaluationFailureKind.USAGE_LIMIT.value: 1}
    assert report.infrastructure_failure_kind_mix == {EvaluationFailureKind.USAGE_LIMIT.value: 1}
    assert report.tasks[0].failure_kind == EvaluationFailureKind.USAGE_LIMIT
    assert report.tasks[0].attempt_count == 1
