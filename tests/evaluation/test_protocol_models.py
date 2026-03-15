from __future__ import annotations

import pytest

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


def test_benchmark_protocol_requires_task_repository_profile_match() -> None:
    with pytest.raises(ValueError, match="task_protocol"):
        BenchmarkProtocol(
            protocol_name="demo",
            agent_family="codex",
            conditions=(
                BenchmarkCondition(
                    name="treatment",
                    arm="suitcode",
                    native_agent_tools=("codex_exec",),
                    suitcode_enabled=True,
                    suitcode_tools_available=True,
                    prompt_policy="strict",
                    sandbox_mode="danger-full-access",
                    approval_mode="dangerous_bypass",
                ),
                BenchmarkCondition(
                    name="baseline",
                    arm="baseline",
                    native_agent_tools=("codex_exec",),
                    suitcode_enabled=False,
                    suitcode_tools_available=False,
                    prompt_policy="native",
                    sandbox_mode="danger-full-access",
                    approval_mode="dangerous_bypass",
                ),
            ),
            task_protocols=(
                TaskProtocol(
                    task_id="task-1",
                    task_family="truth_coverage",
                    task_taxonomy=TaskTaxonomy.TRUTH_COVERAGE,
                    repository_path="repo-a",
                    difficulty="easy",
                    run_temperature=RunTemperature.COLD,
                    question="question",
                    required_tools=("open_workspace", "get_truth_coverage"),
                    expected_ground_truth_kind=GroundTruthKind.EXACT_FIELD_MATCH,
                    expected_success_criteria=("schema valid",),
                ),
            ),
            repository_profiles=(
                RepositoryProfile(
                    repository_path="repo-b",
                    ecosystem="python",
                    language_hint="python",
                    build_tool="python",
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
                    description="desc",
                    reported_in_headline=True,
                    is_primary=True,
                ),
            ),
            timeout_policy="240s",
            session_policy="cold",
            cache_policy="none",
            repo_state_policy="pinned",
        )


def test_task_protocol_requires_success_criteria() -> None:
    with pytest.raises(ValueError, match="expected_success_criteria"):
        TaskProtocol(
            task_id="task-1",
            task_family="truth_coverage",
            task_taxonomy=TaskTaxonomy.TRUTH_COVERAGE,
            repository_path="repo-a",
            difficulty="easy",
            run_temperature=RunTemperature.COLD,
            question="question",
            required_tools=("open_workspace",),
            expected_ground_truth_kind=GroundTruthKind.EXACT_FIELD_MATCH,
            expected_success_criteria=(),
        )


def test_repository_profile_rejects_negative_action_counts() -> None:
    with pytest.raises(ValueError, match="counts must be >= 0"):
        RepositoryProfile(
            repository_path="repo-a",
            ecosystem="python",
            language_hint="python",
            deterministic_action_count=-1,
            build_tool="python",
            architecture_basis="provider-backed",
            test_discovery_basis="provider-backed",
            quality_basis="provider-backed",
        )
