from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import report_hybrid_study, report_live_study, run_live_study
from suitcode.analytics.token_economics import TokenEconomicsRecorder
from suitcode.evaluation.live_study import LiveStudyLauncher
from suitcode.evaluation.models import ActionScore, AnswerScore, CodexEvaluationReport, CodexEvaluationTaskResult, EvaluationStatus, ToolSelectionScore


def test_run_live_study_script_prepares_manifest_and_env(monkeypatch, capsys, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(run_live_study, "LiveStudyLauncher", lambda: LiveStudyLauncher())
    monkeypatch.setattr(
        "suitcode.evaluation.live_study.TrackedStudyRepositoryResolver.resolve",
        lambda self, tracked_label, repository_root: type(
            "_Repo",
            (),
            {"label": "repo", "repository_root": str(repo)},
        )(),
    )
    monkeypatch.setattr(sys, "argv", ["run_live_study", "--repository-root", str(repo), "--task-kind", "discovery", "--json"])

    run_live_study.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["manifest"]["task_kind"] == "discovery"
    assert payload["env"]["SUITCODE_STUDY_KIND"] == "live_session"
    assert Path(payload["manifest_path"]).exists()


def test_report_live_study_uses_manifest_analytics_run_id(monkeypatch, capsys, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    launcher = LiveStudyLauncher()
    monkeypatch.setattr(
        "suitcode.evaluation.live_study.TrackedStudyRepositoryResolver.resolve",
        lambda self, tracked_label, repository_root: type(
            "_Repo",
            (),
            {"label": "repo", "repository_root": str(repo)},
        )(),
    )
    manifest, _, manifest_path = launcher.prepare_launch(
        tracked_label=None,
        repository_root=str(repo),
        task_id="task:live",
        task_kind="discovery",
        study_kind="live_session",
        experiment_id="exp",
        experiment_label="label",
        model_name=None,
        workspace_mode="read_only",
        notes=None,
    )
    recorder = TokenEconomicsRecorder(analytics_run_id=manifest.analytics_run_id)
    recorder.record_success(
        repository_root=repo,
        session_id="session:live",
        task_id="task:live",
        task_kind="discovery",
        study_kind="live_session",
        tool_name="understand_repository",
        arguments={"repository_path": str(repo)},
        result={"repository": {"component_count": 1, "file_count": 1}},
        started_at=1_700_000_000.0,
        duration_ms=10,
    )
    monkeypatch.setattr(sys, "argv", ["report_live_study", "--repository-root", str(repo), "--manifest-path", str(manifest_path), "--json"])

    report_live_study.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["manifest"]["analytics_run_id"] == manifest.analytics_run_id
    assert payload["report"]["total"]["event_count"] == 1


def test_report_hybrid_study_combines_live_and_controlled(monkeypatch, capsys, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        "suitcode.evaluation.live_study.TrackedStudyRepositoryResolver.resolve",
        lambda self, tracked_label, repository_root: type(
            "_Repo",
            (),
            {"label": "repo", "repository_root": str(repo)},
        )(),
    )
    launcher = LiveStudyLauncher()
    manifest, _, _ = launcher.prepare_launch(
        tracked_label=None,
        repository_root=str(repo),
        task_id="task:hybrid",
        task_kind="discovery",
        study_kind="live_session",
        experiment_id="exp",
        experiment_label="label",
        model_name=None,
        workspace_mode="read_only",
        notes=None,
    )
    recorder = TokenEconomicsRecorder(analytics_run_id=manifest.analytics_run_id)
    recorder.record_success(
        repository_root=repo,
        session_id="session:hybrid",
        task_id="task:hybrid",
        task_kind="discovery",
        study_kind="live_session",
        tool_name="understand_repository",
        arguments={"repository_path": str(repo)},
        result={"repository": {"component_count": 1, "file_count": 1}},
        started_at=1_700_000_000.0,
        duration_ms=10,
    )

    class _FakeService:
        def __init__(self, working_directory=None) -> None:
            pass

        def load_report(self, report_id: str):
            return self.load_latest_report()

        def load_latest_report_for_tracked_repository(self, tracked_repository_label: str):
            return self.load_latest_report()

        def load_latest_report(self):
            return CodexEvaluationReport(
                report_id="codex-eval-demo",
                generated_at_utc="2026-04-23T10:00:00.000Z",
                tracked_repository_labels=("mygamesanywhere",),
                task_kind_mix={"planning": 1},
                study_kind_mix={"live_project_controlled": 1},
                task_total=1,
                task_passed=1,
                task_failed=0,
                task_error=0,
                avg_duration_ms=100.0,
                required_tool_success_rate=1.0,
                high_value_tool_early_rate=1.0,
                answer_schema_success_rate=1.0,
                deterministic_action_success_rate=0.0,
                tasks=(
                    CodexEvaluationTaskResult(
                        task_id="controlled-1",
                        task_family="proof_gap",
                        tracked_repository_label="mygamesanywhere",
                        task_kind="validation",
                        study_kind="live_project_controlled",
                        status=EvaluationStatus.PASSED,
                        repository_root=str(repo),
                        duration_ms=100,
                        required_tool_count=1,
                        tool_selection=ToolSelectionScore(required_tools_present=True, required_tool_names=("what_is_not_proven",), used_tool_names=("what_is_not_proven",)),
                        answer_score=AnswerScore(schema_valid=True),
                        action_score=ActionScore(executed=False, matched_target=False),
                        stdout_jsonl_path="stdout.jsonl",
                        output_last_message_path="last_message.txt",
                    ),
                ),
            )

    monkeypatch.setattr(report_hybrid_study, "CodexEvaluationService", _FakeService)
    monkeypatch.setattr(sys, "argv", ["report_hybrid_study", "--repository-root", str(repo), "--latest-controlled", "--json"])

    report_hybrid_study.main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["tracked_repository_label"] == "repo"
    assert payload["controlled_tasks"]["report_id"] == "codex-eval-demo"
    assert payload["live_sessions"]["total"]["event_count"] == 1
