from __future__ import annotations

import sys

from scripts import analyze_codex_comparison
from suitcode.evaluation.comparison_models import (
    ArmRunReference,
    CodexStandoutReport,
    ComparisonDelta,
    EvaluationArm,
    SuiteRole,
)


def test_analyze_codex_comparison_outputs_latest(monkeypatch, capsys) -> None:
    class _FakeService:
        def load_latest_report(self):
            return CodexStandoutReport(
                report_id="codex-comparison-demo",
                generated_at_utc="2026-03-09T15:00:00.000Z",
                model="o3",
                stable_readonly_suitcode=ArmRunReference(
                    arm=EvaluationArm.SUITCODE,
                    suite_role=SuiteRole.STABLE_READONLY,
                    report_id="codex-eval-a",
                    task_total=8,
                    task_passed=8,
                    task_failed=0,
                    task_error=0,
                ),
                stable_readonly_baseline=ArmRunReference(
                    arm=EvaluationArm.BASELINE,
                    suite_role=SuiteRole.STABLE_READONLY,
                    report_id="codex-eval-b",
                    task_total=8,
                    task_passed=5,
                    task_failed=3,
                    task_error=0,
                ),
                stable_execution_suitcode=ArmRunReference(
                    arm=EvaluationArm.SUITCODE,
                    suite_role=SuiteRole.STABLE_EXECUTION,
                    report_id="codex-eval-c",
                    task_total=2,
                    task_passed=2,
                    task_failed=0,
                    task_error=0,
                ),
                stress_readonly_suitcode=None,
                headline_deltas=(
                    ComparisonDelta(
                        metric_name="task_success_rate",
                        suitcode_value=1.0,
                        baseline_value=0.625,
                        delta_absolute=0.375,
                        delta_ratio=0.6,
                        direction="better",
                    ),
                ),
                stable_readonly_summary={"task_total": 8},
                stable_execution_summary={"task_total": 2},
                stress_summary=None,
                passive_usage_summary={"session_count": 4},
                methodology={"headline_comparison": "stable_readonly"},
                limitations=("tokens are transcript estimates",),
                repro_commands=("python scripts/run_codex_comparison.py",),
            )

        def load_report(self, report_id: str):
            return self.load_latest_report()

    monkeypatch.setattr(analyze_codex_comparison, "CodexComparisonService", lambda working_directory=None: _FakeService())
    monkeypatch.setattr(sys, "argv", ["analyze_codex_comparison", "--latest"])

    analyze_codex_comparison.main()
    output = capsys.readouterr().out

    assert "Codex Standout Comparison" in output
    assert "Stable read-only A/B" in output
    assert "Headline deltas:" in output
    assert "Methodology:" in output
    assert "Limitations:" in output
