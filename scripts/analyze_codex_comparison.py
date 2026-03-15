from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from suitcode.evaluation.codex.comparison_service import CodexComparisonService


def _print_agent_metadata(label: str, *, metadata) -> None:
    print(f"{label}:")
    print(
        f"  agent={metadata.agent_kind.value}, cli={metadata.cli_name} {metadata.cli_version or '(unknown)'}, "
        f"model={metadata.model_name or '(unknown)'}, provider={metadata.model_provider or '(unknown)'}"
    )
    print(
        f"  host_os={metadata.host_os}, cwd={metadata.working_directory}, "
        f"transport={metadata.mcp_transport or '(none)'}, suitcode_enabled={metadata.suitcode_enabled}"
    )
    print(
        f"  sandbox={metadata.sandbox_mode or '(default)'}, full_auto={metadata.full_auto}, "
        f"bypass={metadata.bypass_approvals_and_sandbox}, profile={metadata.profile_name or '(none)'}"
    )
    print(
        f"  git_commit={metadata.git_commit_hash or '(unknown)'}, git_branch={metadata.git_branch or '(unknown)'}, "
        f"git_remote={metadata.git_repository_url or '(unknown)'}"
    )
    print(f"  command_prefix={' '.join(metadata.command_prefix) if metadata.command_prefix else '(unknown)'}")
    if metadata.config_overrides:
        print(f"  config_overrides={list(metadata.config_overrides)}")


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
    print("Evaluation scope:")
    for key, value in report.evaluation_scope.items():
        print(f"  {key}: {value}")
    print()
    if report.stable_readonly_suitcode_metadata is not None:
        _print_agent_metadata("SuitCode arm metadata", metadata=report.stable_readonly_suitcode_metadata)
    if report.stable_readonly_baseline_metadata is not None:
        _print_agent_metadata("Baseline arm metadata", metadata=report.stable_readonly_baseline_metadata)
    print(
        "Headline downstream A/B: "
        f"SuitCode {report.stable_readonly_suitcode.task_passed}/{report.stable_readonly_suitcode.task_total}, "
        f"baseline {report.stable_readonly_baseline.task_passed}/{report.stable_readonly_baseline.task_total}"
    )
    if report.calibration_suitcode is not None and report.calibration_baseline is not None:
        print(
            "Calibration A/B: "
            f"SuitCode {report.calibration_suitcode.task_passed}/{report.calibration_suitcode.task_total}, "
            f"baseline {report.calibration_baseline.task_passed}/{report.calibration_baseline.task_total}"
        )
    if report.stable_execution_suitcode is not None:
        print(
            "Stable execution A/B: "
            f"SuitCode {report.stable_execution_suitcode.task_passed}/{report.stable_execution_suitcode.task_total}, "
            f"baseline {report.stable_execution_baseline.task_passed}/{report.stable_execution_baseline.task_total}"
            if report.stable_execution_baseline is not None
            else f"Stable execution: {report.stable_execution_suitcode.task_passed}/{report.stable_execution_suitcode.task_total}"
        )
    if report.stress_readonly_suitcode is not None:
        print(
            "Stress read-only: "
            f"{report.stress_readonly_suitcode.task_passed}/{report.stress_readonly_suitcode.task_total}"
        )
    print()
    print("Benchmark protocol:")
    print(f"- protocol_name: {report.protocol.protocol_name}")
    print(f"- timeout_policy: {report.protocol.timeout_policy}")
    print(f"- session_policy: {report.protocol.session_policy}")
    print(f"- cache_policy: {report.protocol.cache_policy}")
    print(f"- repo_state_policy: {report.protocol.repo_state_policy}")
    print()
    print("Conditions:")
    for item in report.protocol.conditions:
        print(
            f"- {item.name}: arm={item.arm}, suitcode_enabled={item.suitcode_enabled}, "
            f"suitcode_tools_available={item.suitcode_tools_available}, native_tools={list(item.native_agent_tools)}"
        )
        print(f"  prompt_policy: {item.prompt_policy}")
    print()
    print("Measured metrics:")
    for item in report.measured_metrics:
        print(f"- {item.metric_name}: unit={item.unit}, headline={item.reported_in_headline}, description={item.description}")
    print()
    print("Estimated metrics:")
    for item in report.estimated_metrics:
        print(f"- {item.metric_name}: unit={item.unit}, headline={item.reported_in_headline}, description={item.description}")
    print()
    print("Derived metrics:")
    for item in report.derived_metrics:
        print(f"- {item.metric_name}: unit={item.unit}, headline={item.reported_in_headline}, description={item.description}")
    print()
    print("Validity notes:")
    for note in report.evaluation_validity_notes:
        print(f"- {note}")
    print()
    print("Terminology:")
    for item in report.terminology:
        print(f"- {item.term}: {item.definition}")
    print()
    print("Figures:")
    for item in report.figures:
        print(f"- {item.title}: section={item.section.value}, svg={item.svg_relative_path}, csv={item.csv_relative_path}")
        print(f"  metric_kinds: {[kind.value for kind in item.metric_kinds]}")
        print(f"  caption: {item.caption}")
        print(f"  interpretation: {item.interpretation}")
    print()
    print("Suite inventory:")
    for suite in report.suite_descriptions:
        print(
            f"- {suite.suite_role.value}: type={suite.suite_type}, file={suite.suite_file}, "
            f"headline={suite.headline_included}, suitcode_only={suite.suitcode_only}"
        )
        print(f"  purpose: {suite.purpose}")
        print(f"  benchmark_role: {suite.benchmark_role_explanation}")
        print(f"  tasks: {', '.join(suite.task_ids)}")
    print()
    print("Task taxonomy:")
    for item in report.protocol.task_protocols:
        print(
            f"- {item.task_id}: taxonomy={item.task_taxonomy.value}, repository={item.repository_path}, "
            f"difficulty={item.difficulty}, temperature={item.run_temperature.value}, ground_truth={item.expected_ground_truth_kind.value}"
        )
        print(f"  success_criteria: {list(item.expected_success_criteria)}")
    print()
    print("Repository profiles:")
    for item in report.protocol.repository_profiles:
        print(
            f"- {item.repository_path}: ecosystem={item.ecosystem}, language={item.language_hint}, "
            f"components={item.component_count}, tests={item.test_count}, build_tool={item.build_tool}"
        )
        print(f"  architecture_basis: {item.architecture_basis}")
        print(f"  test_discovery_basis: {item.test_discovery_basis}")
        print(f"  quality_basis: {item.quality_basis}")
    print()
    print("Repository structural complexity:")
    for item in report.protocol.repository_profiles:
        print(
            f"- {item.repository_path}: shape={item.repository_shape or '-'}, files={item.approximate_file_count}, "
            f"deterministic_actions={item.deterministic_action_count}, test_actions={item.test_action_count}, "
            f"build_actions={item.build_action_count}, runner_actions={item.runner_action_count}"
        )
    print()
    print("Arm policies:")
    for policy in report.arm_policies:
        print(f"- {policy.arm.value}: suitcode_enabled={policy.suitcode_enabled}")
        print(f"  tooling_policy: {policy.tooling_policy}")
        print(f"  prompt_policy: {policy.prompt_policy}")
        print(f"  scoring_policy: {policy.scoring_policy}")
        if policy.baseline_isolation is not None:
            print(f"  baseline_isolation: {policy.baseline_isolation}")
    print()
    print("Headline deltas:")
    for delta in report.headline_deltas:
        print(
            f"- {delta.metric_name}: suitcode={delta.suitcode_value}, baseline={delta.baseline_value}, "
            f"delta={delta.delta_absolute}, direction={delta.direction}"
        )
    print()
    print("Headline efficiency:")
    for item in report.headline_efficiency:
        print(
            f"- {item.metric_name}: baseline={item.baseline_value}, suitcode={item.suitcode_value}, "
            f"hero={item.is_hero_metric}"
        )
        print(f"  interpretation: {item.interpretation}")
    print()
    print("Provenance coverage:")
    for item in report.provenance_coverage:
        print(
            f"- {item.repository_path}: entities={item.evidence_entity_count}, "
            f"authoritative={item.authoritative_ratio:.1%}, derived={item.derived_ratio:.1%}, "
            f"heuristic={item.heuristic_ratio:.1%}, action_capability={item.deterministic_action_capability_ratio:.1%}"
        )
    print()
    print("Suite failure analysis:")
    for explanation in report.suite_failure_explanations:
        print(
            f"- {explanation.suite_role.value}/{explanation.arm.value}: "
            f"passed={explanation.task_passed}, failed={explanation.task_failed}, errored={explanation.task_error}"
        )
        print(f"  summary: {explanation.plain_language_summary}")
        if explanation.failure_kind_mix:
            print(f"  failure_kind_mix: {explanation.failure_kind_mix}")
        for note in explanation.interpretation_notes:
            print(f"  note: {note}")
    print()
    print("Task-level results:")
    for item in report.task_level_summaries:
        print(
            f"- {item.task_id}: suite={item.suite_role.value}, arm={item.arm.value}, "
            f"family={item.task_family}, status={item.status.value}"
        )
        print(
            f"  taxonomy={item.task_taxonomy.value}, ground_truth={item.ground_truth_kind.value}, "
            f"temperature={item.run_temperature.value}, repository_profile={item.repository_profile_label}"
        )
        print(f"  question: {item.question}")
        print(f"  success_criteria: {list(item.expected_success_criteria)}")
        print(f"  repository_path: {item.repository_path}")
        if item.selector_summary is not None:
            print(f"  selector: {item.selector_summary}")
        print(
            "  classification: "
            f"infrastructure={item.is_infrastructure_failure}, "
            f"scoring={item.is_scoring_failure}, answer={item.is_answer_failure}"
        )
        print(f"  explanation: {item.plain_language_explanation}")
        if item.failure_kind is not None:
            print(f"  failure_kind: {item.failure_kind.value}")
        if item.failure_summary is not None:
            print(f"  failure_summary: {item.failure_summary}")
        print(f"  expected_answer: {item.expected_answer}")
        print(f"  actual_answer: {item.actual_answer if item.actual_answer is not None else '-'}")
        if item.field_value_differences:
            print(f"  field_value_differences: {item.field_value_differences}")
        print(f"  duration_ms: {item.duration_ms}")
        print(f"  transcript_tokens: {item.transcript_tokens if item.transcript_tokens is not None else '-'}")
        print(
            "  artifacts: "
            f"report_id={item.report_id}, stdout={item.stdout_jsonl_path}, "
            f"rollout={item.rollout_artifact_path or '-'}, last_message={item.output_last_message_path}"
        )
    print()
    print("Methodology:")
    for key, value in report.methodology.items():
        print(f"- {key}: {value}")
    print()
    print("Threats to validity:")
    for item in report.limitations:
        print(f"- {item}")
    print()
    print("Limitations:")
    print("- This report freezes the protocol shape for Codex before expanding to additional agents.")
    print("- Stable execution is A/B in this revision, but it remains fixture-backed rather than live-repo execution.")
    print("- Passive analytics are supporting evidence and are not used as the primary benchmark source.")


if __name__ == "__main__":
    main()
