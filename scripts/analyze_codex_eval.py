from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.codex.service import CodexEvaluationService


def _print_agent_metadata(prefix: str, *, report_metadata) -> None:
    print(
        f"{prefix}agent={report_metadata.agent_kind.value}, "
        f"cli={report_metadata.cli_name} {report_metadata.cli_version or '(unknown)'}, "
        f"model={report_metadata.model_name or '(unknown)'}, "
        f"provider={report_metadata.model_provider or '(unknown)'}"
    )
    print(
        f"{prefix}host_os={report_metadata.host_os}, "
        f"cwd={report_metadata.working_directory}, "
        f"transport={report_metadata.mcp_transport or '(none)'}, "
        f"suitcode_enabled={report_metadata.suitcode_enabled}"
    )
    print(
        f"{prefix}sandbox={report_metadata.sandbox_mode or '(default)'}, "
        f"full_auto={report_metadata.full_auto}, "
        f"bypass={report_metadata.bypass_approvals_and_sandbox}, "
        f"profile={report_metadata.profile_name or '(none)'}"
    )
    print(
        f"{prefix}git_commit={report_metadata.git_commit_hash or '(unknown)'}, "
        f"git_branch={report_metadata.git_branch or '(unknown)'}, "
        f"git_remote={report_metadata.git_repository_url or '(unknown)'}"
    )
    print(
        f"{prefix}command_prefix={' '.join(report_metadata.command_prefix) if report_metadata.command_prefix else '(unknown)'}"
    )
    if report_metadata.config_overrides:
        print(f"{prefix}config_overrides={list(report_metadata.config_overrides)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyze_codex_eval")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    service = CodexEvaluationService(working_directory=PROJECT_ROOT)
    if args.latest:
        report = service.load_latest_report()
    elif args.report_id is not None:
        report = service.load_report(args.report_id)
    else:
        report = service.load_latest_report()
    if report is None:
        print("No Codex evaluation report found.")
        return
    if args.as_json:
        print(report.model_dump_json(indent=2))
        return
    print("Codex Evaluation Report")
    print("=======================")
    print(f"Report id: {report.report_id}")
    if report.agent_metadata is not None:
        print("Agent metadata:")
        _print_agent_metadata("  ", report_metadata=report.agent_metadata)
    print(f"Tasks total: {report.task_total}, passed: {report.task_passed}, failed: {report.task_failed}, error: {report.task_error}")
    print(f"Required-tool success rate: {report.required_tool_success_rate:.2%}")
    print(f"High-value tool early rate: {report.high_value_tool_early_rate:.2%}")
    print(f"Answer-schema success rate: {report.answer_schema_success_rate:.2%}")
    print(f"Deterministic action success rate: {report.deterministic_action_success_rate:.2%}")
    print(f"Timeout rate: {report.timeout_rate:.2%}")
    print(f"Session artifact resolution rate: {report.session_artifact_resolution_rate:.2%}")
    print(f"Retry rate: {report.retry_rate:.2%} ({report.retried_task_count} retried, {report.post_retry_pass_count} passed after retry)")
    print(
        "Average first-tool positions: "
        f"suitcode={report.avg_first_suitcode_tool_index if report.avg_first_suitcode_tool_index is not None else '(none)'}, "
        f"high_value={report.avg_first_high_value_tool_index if report.avg_first_high_value_tool_index is not None else '(none)'}"
    )
    print(f"Sessions with no high-value tool rate: {report.sessions_with_no_high_value_tool_rate:.2%}")
    print(f"Average transcript tokens: {report.avg_transcript_tokens if report.avg_transcript_tokens is not None else '(none)'}")
    print(f"Failure kind mix: {report.failure_kind_mix}")
    print(f"Infrastructure failure kind mix: {report.infrastructure_failure_kind_mix}")
    print(f"Required-tool timeout mix: {report.required_tool_timeout_mix}")
    print(f"Required-tool failure mix: {report.required_tool_failure_mix}")
    print(f"Correlation quality mix: {report.correlation_quality_mix}")
    print()
    for task in report.tasks:
        print(
            f"{task.task_id}: status={task.status.value}, failure_kind={task.failure_kind.value if task.failure_kind is not None else '-'}, "
            f"first_tool_index={task.first_suitcode_tool_index or '-'}, high_value={task.tool_selection.first_high_value_tool or '-'}@{task.first_high_value_tool_index or '-'}"
        )
        print(
            f"  attempts: count={task.attempt_count}, retry_applied={task.infrastructure_retry_applied}, prior_failures={list(task.attempt_failure_kinds)}"
        )
        if task.failure_summary:
            print(f"  failure: {task.failure_summary}")
        print(
            f"  tools: required={task.required_tool_count}, used_suitcode={task.used_suitcode_tool_count if task.used_suitcode_tool_count is not None else '-'}, "
            f"used_high_value={task.used_high_value_tool_count if task.used_high_value_tool_count is not None else '-'}"
        )
        if task.invocation_command:
            print(f"  command: {' '.join(task.invocation_command)}")
        for trace in task.required_tool_traces:
            print(
                f"  attempt {trace.attempt_number} required_tool[{trace.tool_name}]: called={trace.called}, success={trace.success}, "
                f"timed_out={trace.timed_out}, call_index={trace.call_index if trace.call_index is not None else '-'}, "
                f"duration_ms={trace.correlated_duration_ms if trace.correlated_duration_ms is not None else '-'}"
            )
            if trace.error_excerpt:
                print(f"    error: {trace.error_excerpt}")
        if task.notes:
            for note in task.notes:
                print(f"  note: {note}")


if __name__ == "__main__":
    main()
