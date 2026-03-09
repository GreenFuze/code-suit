from __future__ import annotations

import json
from pathlib import Path

from suitcode.evaluation.comparison_models import CodexStandoutReport
from suitcode.evaluation.models import CodexEvaluationReport, CodexEvaluationTaskResult


class CodexEvaluationReporter:
    def __init__(self, runs_root: Path) -> None:
        self._runs_root = runs_root

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def write_report(
        self,
        report: CodexEvaluationReport,
        *,
        task_metadata: dict[str, dict[str, object]],
    ) -> Path:
        run_dir = self._runs_root / report.report_id
        tasks_dir = run_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for task_id, metadata in task_metadata.items():
            (tasks_dir / task_id / "metadata.json").parent.mkdir(parents=True, exist_ok=True)
            (tasks_dir / task_id / "metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        report_path = run_dir / "report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report_path

    def load_report(self, report_id: str) -> CodexEvaluationReport:
        report_path = self._runs_root / report_id / "report.json"
        if not report_path.exists():
            raise ValueError(f"Codex evaluation report not found: `{report_id}`")
        return CodexEvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    def load_latest_report(self) -> CodexEvaluationReport | None:
        if not self._runs_root.exists():
            return None
        candidates = sorted(
            self._runs_root.glob("*/report.json"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        if not candidates:
            return None
        return CodexEvaluationReport.model_validate_json(candidates[0].read_text(encoding="utf-8"))


class CodexComparisonReporter:
    def __init__(self, comparisons_root: Path) -> None:
        self._comparisons_root = comparisons_root

    @property
    def comparisons_root(self) -> Path:
        return self._comparisons_root

    def write_report(
        self,
        report: CodexStandoutReport,
        *,
        comparison_markdown: str,
        inputs: dict[str, object],
    ) -> Path:
        run_dir = self._comparisons_root / report.report_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "comparison.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        (run_dir / "comparison.md").write_text(comparison_markdown, encoding="utf-8")
        (run_dir / "inputs.json").write_text(json.dumps(inputs, indent=2, sort_keys=True), encoding="utf-8")
        return run_dir / "comparison.json"

    def load_report(self, report_id: str) -> CodexStandoutReport:
        report_path = self._comparisons_root / report_id / "comparison.json"
        if not report_path.exists():
            raise ValueError(f"Codex comparison report not found: `{report_id}`")
        return CodexStandoutReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    def load_latest_report(self) -> CodexStandoutReport | None:
        if not self._comparisons_root.exists():
            return None
        candidates = sorted(
            self._comparisons_root.glob("*/comparison.json"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        if not candidates:
            return None
        return CodexStandoutReport.model_validate_json(candidates[0].read_text(encoding="utf-8"))
