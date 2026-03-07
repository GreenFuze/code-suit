from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.analytics.benchmark import BenchmarkHarness, SuitCodeBenchmarkAdapter
from suitcode.analytics.settings import AnalyticsSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_mcp_benchmark")
    parser.add_argument("--tasks-file", default="benchmarks/tasks/sample_tasks.json")
    parser.add_argument(
        "--fail-on-task-error",
        action="store_true",
        help="Exit with code 1 when benchmark report contains failed/error tasks.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tasks_file = Path(args.tasks_file).expanduser().resolve()
    if not tasks_file.exists():
        raise ValueError(f"benchmark tasks file not found: `{tasks_file}`")

    settings = AnalyticsSettings.from_env()
    harness = BenchmarkHarness(settings.global_root)
    tasks = harness.load_tasks(tasks_file)
    report = harness.run(SuitCodeBenchmarkAdapter(working_directory=PROJECT_ROOT), tasks)
    print(f"Generated benchmark report: {report.report_id}")
    print(f"Adapter: {report.adapter_name}")
    print(f"Tasks total: {report.task_total}, passed: {report.task_passed}, failed: {report.task_failed}, error: {report.task_error}")
    if args.fail_on_task_error and (report.task_failed > 0 or report.task_error > 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
