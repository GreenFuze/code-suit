from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.codex.service import CodexEvaluationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_codex_eval")
    parser.add_argument("--tasks-file", default="benchmarks/codex/tasks/suitcode_native.json")
    parser.add_argument("--task-id", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--codex-config-profile", default=None)
    parser.add_argument("--fail-on-task-failure", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--no-full-auto", action="store_true")
    parser.add_argument("--sandbox", default="workspace-write")
    parser.add_argument("--bypass-approvals-and-sandbox", action="store_true")
    parser.add_argument("--auto-orientation-hint", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tasks_file = Path(args.tasks_file).expanduser().resolve()
    if not tasks_file.exists():
        raise ValueError(f"Codex evaluation tasks file not found: `{tasks_file}`")
    service = CodexEvaluationService(working_directory=PROJECT_ROOT)
    tasks = service.load_tasks(tasks_file)
    if args.task_id is not None:
        tasks = tuple(item for item in tasks if item.task_id == args.task_id)
        if not tasks:
            raise ValueError(f"task_id not found in tasks file: `{args.task_id}`")
    if args.timeout_seconds is not None:
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be > 0")
        tasks = tuple(item.model_copy(update={"timeout_seconds": args.timeout_seconds}) for item in tasks)
    report = service.run(
        tasks,
        model=args.model,
        profile=args.codex_config_profile,
        full_auto=not args.no_full_auto,
        sandbox=args.sandbox,
        bypass_approvals_and_sandbox=args.bypass_approvals_and_sandbox,
        auto_orientation_hint=args.auto_orientation_hint,
    )
    if args.as_json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"Generated Codex evaluation report: {report.report_id}")
        print(f"Tasks total: {report.task_total}, passed: {report.task_passed}, failed: {report.task_failed}, error: {report.task_error}")
        print(f"Required-tool success rate: {report.required_tool_success_rate:.2%}")
        print(f"High-value tool early rate: {report.high_value_tool_early_rate:.2%}")
        print(f"Answer-schema success rate: {report.answer_schema_success_rate:.2%}")
        print(f"Deterministic action success rate: {report.deterministic_action_success_rate:.2%}")
        print(f"Average transcript tokens: {report.avg_transcript_tokens if report.avg_transcript_tokens is not None else '(none)'}")
    if args.fail_on_task_failure and (report.task_failed > 0 or report.task_error > 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
