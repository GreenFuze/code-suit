from __future__ import annotations

import sys

from scripts import analyze_codex_comparison
from suitcode.evaluation.comparison_models import (
    ArmPolicyDescription,
    ArmRunReference,
    CodexStandoutReport,
    ComparisonDelta,
    ComparisonFigure,
    ComparisonFigureSection,
    EvaluationArm,
    HeadlineEfficiencyMetric,
    ProvenanceCoverageSummary,
    SuiteDescription,
    SuiteFailureExplanation,
    SuiteRole,
    TaskFailureExplanation,
    TerminologyEntry,
)
from suitcode.evaluation.models import EvaluationFailureKind, EvaluationStatus
from suitcode.evaluation.protocol_models import (
    BenchmarkCondition,
    BenchmarkProtocol,
    GroundTruthKind,
    MetricDefinition,
    MetricKind,
    RepositoryProfile,
    RunTemperature,
    TaskProtocol,
    TaskTaxonomy,
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
                evaluation_scope={"agent_scope": "codex_only"},
                protocol=BenchmarkProtocol(
                    protocol_name="demo",
                    agent_family="codex",
                    agent_version="0.106.0",
                    model_name="o3",
                    model_provider="openai",
                    conditions=(
                        BenchmarkCondition(
                            name="treatment",
                            arm="suitcode",
                            native_agent_tools=("codex_exec", "filesystem", "shell", "mcp"),
                            suitcode_enabled=True,
                            suitcode_tools_available=True,
                            prompt_policy="neutral",
                            sandbox_mode="danger-full-access",
                            approval_mode="dangerous_bypass",
                        ),
                        BenchmarkCondition(
                            name="baseline",
                            arm="baseline",
                            native_agent_tools=("codex_exec", "filesystem", "shell"),
                            suitcode_enabled=False,
                            suitcode_tools_available=False,
                            prompt_policy="native-only",
                            sandbox_mode="danger-full-access",
                            approval_mode="dangerous_bypass",
                        ),
                    ),
                    task_protocols=(
                        TaskProtocol(
                            task_id="python-orientation-headline",
                            task_family="orientation",
                            task_taxonomy=TaskTaxonomy.ORIENTATION,
                            repository_path="tests/test_repos/python",
                            difficulty="easy",
                            run_temperature=RunTemperature.COLD,
                            question="What is the repository summary?",
                            required_tools=("open_workspace", "repository_summary", "get_truth_coverage"),
                            expected_ground_truth_kind=GroundTruthKind.EXACT_FIELD_MATCH,
                            expected_success_criteria=("schema valid", "field exact"),
                        ),
                    ),
                    repository_profiles=(
                        RepositoryProfile(
                            repository_path="tests/test_repos/python",
                            ecosystem="python",
                            language_hint="python",
                            approximate_file_count=62,
                            component_count=1,
                            test_count=4,
                            deterministic_action_count=3,
                            test_action_count=1,
                            build_action_count=1,
                            runner_action_count=1,
                            build_tool="python",
                            repository_shape="single-service fixture",
                            architecture_basis="provider-backed",
                            test_discovery_basis="provider-backed",
                            quality_basis="provider-backed",
                        ),
                    ),
                    metric_definitions=(
                        MetricDefinition(
                            metric_name="task_success_rate",
                            metric_kind=MetricKind.MEASURED,
                            unit="rate",
                            description="task success",
                            reported_in_headline=True,
                            is_primary=True,
                        ),
                        MetricDefinition(
                            metric_name="avg_transcript_tokens",
                            metric_kind=MetricKind.ESTIMATED,
                            unit="tokens",
                            description="estimated tokens",
                            reported_in_headline=True,
                            is_primary=True,
                        ),
                        MetricDefinition(
                            metric_name="success_normalized_token_cost",
                            metric_kind=MetricKind.DERIVED,
                            unit="tokens_per_pass",
                            description="derived cost",
                            reported_in_headline=True,
                            is_primary=False,
                        ),
                    ),
                    timeout_policy="240s",
                    session_policy="cold",
                    cache_policy="none",
                    repo_state_policy="pinned",
                ),
                measured_metrics=(
                    MetricDefinition(
                        metric_name="task_success_rate",
                        metric_kind=MetricKind.MEASURED,
                        unit="rate",
                        description="task success",
                        reported_in_headline=True,
                        is_primary=True,
                    ),
                ),
                estimated_metrics=(
                    MetricDefinition(
                        metric_name="avg_transcript_tokens",
                        metric_kind=MetricKind.ESTIMATED,
                        unit="tokens",
                        description="estimated tokens",
                        reported_in_headline=True,
                        is_primary=True,
                    ),
                ),
                derived_metrics=(
                    MetricDefinition(
                        metric_name="success_normalized_token_cost",
                        metric_kind=MetricKind.DERIVED,
                        unit="tokens_per_pass",
                        description="derived cost",
                        reported_in_headline=True,
                        is_primary=False,
                    ),
                ),
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
                headline_efficiency=(
                    HeadlineEfficiencyMetric(
                        metric_name="Median turns per stable headline task",
                        baseline_value="4",
                        suitcode_value="2",
                        interpretation="Primary A/B efficiency metric.",
                        is_hero_metric=True,
                    ),
                    HeadlineEfficiencyMetric(
                        metric_name="Median turns to correct deterministic action",
                        baseline_value="not reported",
                        suitcode_value="3",
                        interpretation="Treatment only.",
                    ),
                ),
                provenance_coverage=(
                    ProvenanceCoverageSummary(
                        repository_profile_label="tests/test_repos/python",
                        repository_path="tests/test_repos/python",
                        scope="calibration_treatment_truth_coverage",
                        evidence_entity_count=27,
                        authoritative_count=15,
                        derived_count=12,
                        heuristic_count=0,
                        authoritative_ratio=15 / 27,
                        derived_ratio=12 / 27,
                        heuristic_ratio=0.0,
                        deterministic_action_capability_count=2,
                        deterministic_action_capability_total=3,
                        deterministic_action_capability_ratio=2 / 3,
                    ),
                ),
                figures=(
                    ComparisonFigure(
                        figure_id="figure-01-headline-outcomes",
                        title="Figure 1. Headline A/B Outcomes",
                        section=ComparisonFigureSection.MAIN,
                        caption="headline outcomes",
                        interpretation="suitcode wins",
                        svg_relative_path="figures/01-headline-outcomes.svg",
                        csv_relative_path="figures/data/01-headline-outcomes.csv",
                        source_scope="stable_readonly",
                        metric_kinds=(MetricKind.MEASURED,),
                        depends_on_sections=("Headline A/B: Downstream Developer Tasks",),
                    ),
                ),
                terminology=(
                    TerminologyEntry(term="Stable read-only", definition="headline bounded suite"),
                ),
                suite_descriptions=(
                    SuiteDescription(
                        suite_role=SuiteRole.STABLE_READONLY,
                        suite_type="headline_ab",
                        suite_file="benchmarks/codex/tasks/suitcode_v6_headline.json",
                        headline_included=True,
                        suitcode_only=False,
                        purpose="headline suite",
                        benchmark_role_explanation="headline comparison",
                        task_ids=("project-python-change-impact-headline", "project-python-minimum-verified-headline"),
                    ),
                ),
                arm_policies=(
                    ArmPolicyDescription(
                        arm=EvaluationArm.SUITCODE,
                        suitcode_enabled=True,
                        tooling_policy="SuitCode available",
                        prompt_policy="neutral",
                        scoring_policy="tool + answer scoring",
                    ),
                ),
                suite_failure_explanations=(
                    SuiteFailureExplanation(
                        suite_role=SuiteRole.STABLE_READONLY,
                        arm=EvaluationArm.BASELINE,
                        task_total=8,
                        task_passed=5,
                        task_failed=3,
                        task_error=0,
                        failure_kind_mix={"answer_mismatch": 3},
                        plain_language_summary="baseline had three answer mismatches",
                        interpretation_notes=("stress skip is unrelated",),
                    ),
                ),
                task_level_summaries=(
                    TaskFailureExplanation(
                        task_id="project-python-change-impact-headline",
                        suite_role=SuiteRole.STABLE_READONLY,
                        arm=EvaluationArm.BASELINE,
                        task_family="change_analysis",
                        task_taxonomy=TaskTaxonomy.IMPACT_ANALYSIS,
                        ground_truth_kind=GroundTruthKind.EXACT_FIELD_MATCH,
                        expected_success_criteria=("schema valid", "field exact"),
                        run_temperature=RunTemperature.COLD,
                        repository_profile_label=".",
                        repository_path=".",
                        question="If src/suitcode/mcp/service.py changes, what is the deterministic impact summary?",
                        selector_summary="repository_rel_path=src/suitcode/mcp/service.py",
                        status=EvaluationStatus.FAILED,
                        failure_kind=EvaluationFailureKind.ANSWER_MISMATCH,
                        failure_summary="mismatched=owner_id",
                        plain_language_explanation="schema-valid but incorrect answer",
                        is_infrastructure_failure=False,
                        is_scoring_failure=False,
                        is_answer_failure=True,
                        transcript_tokens=1234,
                        duration_ms=1000,
                        expected_answer={"owner_id": "component:python:suitcode"},
                        actual_answer={"owner_id": "component:python:wrong"},
                        field_value_differences={"owner_id": {"expected": "component:python:suitcode", "actual": "component:python:wrong"}},
                        report_id="codex-eval-b",
                        stdout_jsonl_path="stdout.jsonl",
                        rollout_artifact_path="rollout.jsonl",
                        output_last_message_path="last_message.txt",
                    ),
                ),
                evaluation_validity_notes=("baseline failures are unrelated to skipped stress",),
                methodology={"headline_comparison": "stable_readonly_downstream_ab"},
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
    assert "Headline downstream A/B" in output
    assert "Validity notes:" in output
    assert "Evaluation scope:" in output
    assert "Benchmark protocol:" in output
    assert "Measured metrics:" in output
    assert "Estimated metrics:" in output
    assert "Derived metrics:" in output
    assert "Terminology:" in output
    assert "Figures:" in output
    assert "Figure 1. Headline A/B Outcomes" in output
    assert "Suite inventory:" in output
    assert "Task taxonomy:" in output
    assert "Repository profiles:" in output
    assert "Repository structural complexity:" in output
    assert "Provenance coverage:" in output
    assert "Arm policies:" in output
    assert "Headline deltas:" in output
    assert "Headline efficiency:" in output
    assert "Suite failure analysis:" in output
    assert "Task-level results:" in output
    assert "question:" in output
    assert "expected_answer:" in output
    assert "actual_answer:" in output
    assert "field_value_differences:" in output
    assert "Methodology:" in output
    assert "Threats to validity:" in output
    assert "Limitations:" in output
