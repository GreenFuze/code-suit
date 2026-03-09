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
    parser = argparse.ArgumentParser(prog="run_codex_comparison")
    parser.add_argument("--spec-file", default="benchmarks/codex/comparisons/standout_codex.json")
    parser.add_argument("--model", default=None)
    parser.add_argument("--profile-suitcode", default=None)
    parser.add_argument("--profile-baseline", default=None)
    parser.add_argument("--stable-timeout-seconds", type=int, default=None)
    parser.add_argument("--stress-timeout-seconds", type=int, default=None)
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--skip-execution", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = CodexComparisonService(working_directory=PROJECT_ROOT)
    spec_path = (PROJECT_ROOT / args.spec_file).expanduser().resolve()
    if not spec_path.exists():
        raise ValueError(f"Codex comparison spec not found: `{spec_path}`")
    spec = service.load_spec(spec_path)
    report = service.run_standout_report(
        spec,
        model=args.model,
        profile_suitcode=args.profile_suitcode,
        profile_baseline=args.profile_baseline,
        stable_timeout_seconds=args.stable_timeout_seconds,
        stress_timeout_seconds=args.stress_timeout_seconds,
        skip_stress=args.skip_stress,
        skip_execution=args.skip_execution,
    )
    if args.as_json:
        print(report.model_dump_json(indent=2))
        return
    print(f"Generated Codex standout comparison: {report.report_id}")
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
    for delta in report.headline_deltas:
        print(
            f"{delta.metric_name}: suitcode={delta.suitcode_value}, baseline={delta.baseline_value}, "
            f"direction={delta.direction}"
        )


if __name__ == "__main__":
    main()
