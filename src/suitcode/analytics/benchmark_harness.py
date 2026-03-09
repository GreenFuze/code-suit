from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from suitcode.analytics.models import BenchmarkReport, BenchmarkTaskResult
from suitcode.core.truth_coverage_models import TruthCoverageSummary


@dataclass(frozen=True)
class BenchmarkTaskRun:
    result: BenchmarkTaskResult
    metadata: dict[str, object]


class BenchmarkAdapter(Protocol):
    @property
    def name(self) -> str:
        ...

    def run_task(self, task: dict[str, object], *, run_id: str, task_artifact_path: Path) -> BenchmarkTaskRun:
        ...


class BenchmarkHarness:
    def __init__(self, benchmark_root: Path) -> None:
        self._benchmark_root = benchmark_root

    def load_tasks(self, tasks_file: Path) -> tuple[dict[str, object], ...]:
        payload = json.loads(tasks_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("benchmark tasks file must contain a JSON list")
        tasks: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("each benchmark task must be an object")
            task_id = item.get("task_id")
            repository_path = item.get("repository_path")
            workflow = item.get("workflow")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("benchmark task missing non-empty `task_id`")
            if not isinstance(repository_path, str) or not repository_path.strip():
                raise ValueError(f"benchmark task `{task_id}` missing non-empty `repository_path`")
            if not isinstance(workflow, str) or not workflow.strip():
                raise ValueError(f"benchmark task `{task_id}` missing non-empty `workflow`")
            tasks.append(item)
        return tuple(tasks)

    def run(self, adapter: BenchmarkAdapter, tasks: tuple[dict[str, object], ...]) -> BenchmarkReport:
        run_id = f"benchmark-{uuid4().hex}"
        run_dir = self._benchmark_root / "benchmarks" / run_id
        task_dir = run_dir / "tasks"
        task_runs = tuple(
            adapter.run_task(
                task,
                run_id=run_id,
                task_artifact_path=task_dir / f"{_required_string(task, 'task_id')}.json",
            )
            for task in tasks
        )
        results = tuple(item.result for item in task_runs)
        passed = sum(1 for item in results if item.status == "passed")
        failed = sum(1 for item in results if item.status == "failed")
        errored = sum(1 for item in results if item.status == "error")
        avg_tool_calls = (sum(item.tool_calls for item in results) / len(results)) if results else 0.0
        avg_duration = (sum(item.duration_ms for item in results) / len(results)) if results else 0.0
        truth_coverage = _benchmark_truth_coverage(task_runs)
        report = BenchmarkReport(
            report_id=run_id,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            adapter_name=adapter.name,
            task_total=len(results),
            task_passed=passed,
            task_failed=failed,
            task_error=errored,
            avg_tool_calls=avg_tool_calls,
            avg_duration_ms=avg_duration,
            high_value_tool_usage_rate=high_value_tool_usage_rate(results),
            high_value_tool_early_rate=high_value_tool_early_rate(results),
            deterministic_action_success_rate=deterministic_action_success_rate(results),
            authoritative_provenance_rate=provenance_rate(results, "authoritative"),
            derived_provenance_rate=provenance_rate(results, "derived"),
            heuristic_provenance_rate=provenance_rate(results, "heuristic"),
            truth_coverage=truth_coverage,
            tasks=results,
        )
        self.write_report(report, task_runs=task_runs)
        return report

    def write_report(self, report: BenchmarkReport, *, task_runs: tuple[BenchmarkTaskRun, ...]) -> Path:
        run_dir = self._benchmark_root / "benchmarks" / report.report_id
        task_dir = run_dir / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        for task_run in task_runs:
            task_path = task_dir / f"{task_run.result.task_id}.json"
            task_path.write_text(json.dumps(task_run.metadata, indent=2, sort_keys=True), encoding="utf-8")
        output_file = run_dir / "report.json"
        output_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return output_file


def _required_string(task: dict[str, object], key: str) -> str:
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"benchmark task missing non-empty `{key}`")
    return value.strip()


def high_value_tool_usage_rate(results: tuple[BenchmarkTaskResult, ...]) -> float:
    if not results:
        return 0.0
    return sum(1 for item in results if item.first_high_value_tool is not None) / len(results)


def high_value_tool_early_rate(results: tuple[BenchmarkTaskResult, ...]) -> float:
    if not results:
        return 0.0
    return sum(1 for item in results if item.used_high_value_tool_early) / len(results)


def deterministic_action_success_rate(results: tuple[BenchmarkTaskResult, ...]) -> float:
    applicable = [item for item in results if item.deterministic_action_status != "not_applicable"]
    if not applicable:
        return 0.0
    return sum(1 for item in applicable if item.deterministic_action_status == "passed") / len(applicable)


def provenance_rate(results: tuple[BenchmarkTaskResult, ...], key: str) -> float:
    total = sum(sum(item.provenance_confidence_mix.values()) for item in results)
    if total == 0:
        return 0.0
    count = sum(item.provenance_confidence_mix.get(key, 0) for item in results)
    return count / total


def _benchmark_truth_coverage(task_runs: tuple[BenchmarkTaskRun, ...]) -> TruthCoverageSummary | None:
    for task_run in task_runs:
        payload = task_run.metadata.get("truth_coverage")
        if payload is None:
            continue
        return TruthCoverageSummary.model_validate(payload)
    return None
