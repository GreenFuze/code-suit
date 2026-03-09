from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts import analyze_codex_eval
from suitcode.evaluation.codex.runner import CodexCliRunner
from suitcode.evaluation.codex.service import CodexEvaluationService
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.models import EvaluationFailureKind
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
        return SimpleNamespace(provider_ids=("python",), component_count=1, test_count=2, quality_provider_ids=("ruff",))

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


class _FakeCommandRunner:
    def __init__(self, sessions_root: Path, repository_root: Path) -> None:
        self._sessions_root = sessions_root
        self._repository_root = repository_root

    def __call__(self, command, *, input, text, capture_output, timeout, check):
        output_last_message = Path(command[command.index("--output-last-message") + 1])
        output_last_message.parent.mkdir(parents=True, exist_ok=True)
        output_last_message.write_text(
            json.dumps(
                {
                    "workspace_id": "workspace:demo",
                    "repository_id": "repo:demo",
                    "provider_ids": ["python"],
                    "component_count": 1,
                    "test_count": 2,
                    "quality_provider_count": 1,
                    "overall_truth_availability": "available",
                }
            ),
            encoding="utf-8",
        )
        session_path = self._sessions_root / "2026" / "03" / "08" / "orientation.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            "\n".join(
                (
                    json.dumps({"timestamp": "2026-03-08T10:00:00.000Z", "type": "session_meta", "payload": {"id": "codex-orientation", "timestamp": "2026-03-08T10:00:00.000Z", "cwd": self._repository_root.as_posix(), "model_provider": "openai"}}),
                    json.dumps({"timestamp": "2026-03-08T10:00:01.000Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run"}]}}),
                    json.dumps({"timestamp": "2026-03-08T10:00:02.000Z", "type": "response_item", "payload": {"type": "function_call", "name": "mcp__suitcode__open_workspace", "arguments": '{"repository_path":"%s"}' % self._repository_root.as_posix(), "call_id": "call-1"}}),
                    json.dumps({"timestamp": "2026-03-08T10:00:03.000Z", "type": "response_item", "payload": {"type": "function_call", "name": "mcp__suitcode__repository_summary", "arguments": '{"workspace_id":"workspace:demo","repository_id":"repo:demo"}', "call_id": "call-2"}}),
                    json.dumps({"timestamp": "2026-03-08T10:00:04.000Z", "type": "response_item", "payload": {"type": "function_call", "name": "mcp__suitcode__get_truth_coverage", "arguments": '{"workspace_id":"workspace:demo","repository_id":"repo:demo"}', "call_id": "call-3"}}),
                )
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout='{"event":"ok"}\n', stderr="")


def test_analyze_codex_eval_script_outputs_latest(monkeypatch, capsys, tmp_path: Path) -> None:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    sessions = tmp_path / "sessions"
    service = CodexEvaluationService(
        working_directory=tmp_path,
        runner=CodexCliRunner(sessions_root=sessions, command_runner=_FakeCommandRunner(sessions, repo)),
        reporter=CodexEvaluationReporter(tmp_path / ".suit" / "evaluation" / "codex" / "runs"),
        service_factory=_FakeSuitService,
    )
    service.run((CodexEvaluationTask(task_id="orientation-1", repository_path="repo", task_family=CodexTaskFamily.ORIENTATION, timeout_seconds=120),))

    monkeypatch.setattr(analyze_codex_eval, "CodexEvaluationService", lambda working_directory=None: service)
    monkeypatch.setattr(sys, "argv", ["analyze_codex_eval", "--latest"])

    analyze_codex_eval.main()
    output = capsys.readouterr().out

    assert "Codex Evaluation Report" in output
    assert "orientation-1" in output
    assert "Failure kind mix" in output
    assert "Retry rate" in output


def test_analyze_codex_eval_script_outputs_failure_kind(monkeypatch, capsys, tmp_path: Path) -> None:
    class _FakeService:
        def load_latest_report(self):
            from suitcode.evaluation.models import (
                ActionScore,
                AnswerScore,
                CodexEvaluationReport,
                CodexEvaluationTaskResult,
                EvaluationStatus,
                RequiredToolTrace,
                ToolSelectionScore,
            )

            return CodexEvaluationReport(
                report_id="codex-eval-demo",
                generated_at_utc="2026-03-08T10:00:00.000Z",
                task_total=1,
                task_passed=0,
                task_failed=0,
                task_error=1,
                avg_duration_ms=100.0,
                required_tool_success_rate=0.0,
                high_value_tool_early_rate=0.0,
                answer_schema_success_rate=0.0,
                deterministic_action_success_rate=0.0,
                timeout_rate=1.0,
                session_artifact_resolution_rate=0.0,
                retry_rate=1.0,
                retried_task_count=1,
                post_retry_pass_count=0,
                sessions_with_no_high_value_tool_rate=1.0,
                failure_kind_mix={EvaluationFailureKind.TIMEOUT.value: 1},
                infrastructure_failure_kind_mix={},
                correlation_quality_mix={},
                tasks=(
                    CodexEvaluationTaskResult(
                        task_id="timeout-1",
                        task_family="truth_coverage",
                        status=EvaluationStatus.ERROR,
                        failure_kind=EvaluationFailureKind.TIMEOUT,
                        failure_summary="codex exec timed out after 120 seconds",
                        repository_root=str(tmp_path),
                        duration_ms=120000,
                        attempt_count=2,
                        attempt_failure_kinds=(EvaluationFailureKind.CLI_ERROR.value,),
                        infrastructure_retry_applied=True,
                        required_tool_count=2,
                        tool_selection=ToolSelectionScore(required_tools_present=False, required_tool_names=("open_workspace",), used_tool_names=(), missing_required_tools=("open_workspace",)),
                        answer_score=AnswerScore(schema_valid=False),
                        action_score=ActionScore(executed=False, matched_target=False),
                        required_tool_traces=(
                            RequiredToolTrace(tool_name="open_workspace", attempt_number=1, called=False, success=False),
                            RequiredToolTrace(tool_name="open_workspace", attempt_number=2, called=False, success=False, timed_out=True),
                        ),
                        stdout_jsonl_path="stdout.jsonl",
                        output_last_message_path="last_message.txt",
                    ),
                ),
            )

        def load_report(self, report_id: str):
            return self.load_latest_report()

    monkeypatch.setattr(analyze_codex_eval, "CodexEvaluationService", lambda working_directory=None: _FakeService())
    monkeypatch.setattr(sys, "argv", ["analyze_codex_eval", "--latest"])

    analyze_codex_eval.main()
    output = capsys.readouterr().out

    assert "failure_kind=timeout" in output
    assert "codex exec timed out after 120 seconds" in output
    assert "attempts: count=2, retry_applied=True" in output
    assert "attempt 1 required_tool[open_workspace]" in output
