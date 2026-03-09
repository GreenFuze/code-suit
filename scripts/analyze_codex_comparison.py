from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.codex.comparison_service import CodexComparisonService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_codex_comparison")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = CodexComparisonService(working_directory=PROJECT_ROOT)
    if args.latest or args.report_id is None:
        report = service.load_latest_report()
    else:
        report = service.load_report(args.report_id)
    if report is None:
        print("No Codex comparison report found.")
        return
    if args.as_json:
        print(report.model_dump_json(indent=2))
        return
    print("Codex Standout Comparison")
    print("=========================")
    print(f"Report id: {report.report_id}")
    print(f"Model: {report.model or 'default'}")
    print(
        "Stable read-only A/B: "
        f"SuitCode {report.stable_readonly_suitcode.task_passed}/{report.stable_readonly_suitcode.task_total}, "
        f"baseline {report.stable_readonly_baseline.task_passed}/{report.stable_readonly_baseline.task_total}"
    )
    if report.stable_execution_suitcode is not None:
        print(
            "Stable execution: "
            f"{report.stable_execution_suitcode.task_passed}/{report.stable_execution_suitcode.task_total}"
        )
    if report.stress_readonly_suitcode is not None:
        print(
            "Stress read-only: "
            f"{report.stress_readonly_suitcode.task_passed}/{report.stress_readonly_suitcode.task_total}"
        )
    print()
    print("Headline deltas:")
    for delta in report.headline_deltas:
        print(
            f"- {delta.metric_name}: suitcode={delta.suitcode_value}, baseline={delta.baseline_value}, "
            f"delta={delta.delta_absolute}, direction={delta.direction}"
        )
    print()
    print("Methodology:")
    for key, value in report.methodology.items():
        print(f"- {key}: {value}")
    print()
    print("Limitations:")
    for item in report.limitations:
        print(f"- {item}")


if __name__ == "__main__":
    main()
