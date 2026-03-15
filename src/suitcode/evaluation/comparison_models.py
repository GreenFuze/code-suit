from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.analytics.models import StrictModel
from suitcode.evaluation.models import EvaluationFailureKind, EvaluationStatus
from suitcode.evaluation.metadata_models import AgentRunMetadata
from suitcode.evaluation.protocol_models import (
    BenchmarkProtocol,
    GroundTruthKind,
    MetricDefinition,
    MetricKind,
    RunTemperature,
    TaskTaxonomy,
)


class EvaluationArm(StrEnum):
    SUITCODE = "suitcode"
    BASELINE = "baseline"


class SuiteRole(StrEnum):
    STABLE_READONLY = "stable_readonly"
    CALIBRATION = "calibration"
    STABLE_EXECUTION = "stable_execution"
    STRESS_READONLY = "stress_readonly"


class ComparisonFigureSection(StrEnum):
    MAIN = "main"
    SUPPORTING = "supporting"


class ArmRunReference(StrictModel):
    arm: EvaluationArm
    suite_role: SuiteRole
    report_id: str
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int

    @field_validator("report_id")
    @classmethod
    def _validate_report_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("report_id must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_counts(self) -> "ArmRunReference":
        if any(value < 0 for value in (self.task_total, self.task_passed, self.task_failed, self.task_error)):
            raise ValueError("run reference counts must be >= 0")
        if self.task_passed + self.task_failed + self.task_error != self.task_total:
            raise ValueError("run reference counts are inconsistent")
        return self


class ComparisonDelta(StrictModel):
    metric_name: str
    suitcode_value: float | int | None
    baseline_value: float | int | None
    delta_absolute: float | None = None
    delta_ratio: float | None = None
    direction: str

    @field_validator("metric_name", "direction")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class SuiteDescription(StrictModel):
    suite_role: SuiteRole
    suite_type: str
    suite_file: str
    headline_included: bool
    suitcode_only: bool
    purpose: str
    benchmark_role_explanation: str
    task_ids: tuple[str, ...]

    @field_validator("suite_type", "suite_file", "purpose", "benchmark_role_explanation")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_tasks(self) -> "SuiteDescription":
        if not self.task_ids:
            raise ValueError("suite description must include at least one task_id")
        return self


class ArmPolicyDescription(StrictModel):
    arm: EvaluationArm
    suitcode_enabled: bool
    tooling_policy: str
    baseline_isolation: str | None = None
    prompt_policy: str
    scoring_policy: str

    @field_validator("tooling_policy", "baseline_isolation", "prompt_policy", "scoring_policy")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class TerminologyEntry(StrictModel):
    term: str
    definition: str

    @field_validator("term", "definition")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class ComparisonFigure(StrictModel):
    figure_id: str
    title: str
    section: ComparisonFigureSection
    caption: str
    interpretation: str
    svg_relative_path: str
    csv_relative_path: str
    source_scope: str
    metric_kinds: tuple[MetricKind, ...] = Field(default_factory=tuple)
    depends_on_sections: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator(
        "figure_id",
        "title",
        "caption",
        "interpretation",
        "svg_relative_path",
        "csv_relative_path",
        "source_scope",
    )
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_paths(self) -> "ComparisonFigure":
        if self.svg_relative_path.startswith(("/", "\\")):
            raise ValueError("svg_relative_path must be relative")
        if self.csv_relative_path.startswith(("/", "\\")):
            raise ValueError("csv_relative_path must be relative")
        if not self.svg_relative_path.endswith(".svg"):
            raise ValueError("svg_relative_path must end with .svg")
        if not self.csv_relative_path.endswith(".csv"):
            raise ValueError("csv_relative_path must end with .csv")
        if not self.metric_kinds:
            raise ValueError("metric_kinds must not be empty")
        if not self.depends_on_sections:
            raise ValueError("depends_on_sections must not be empty")
        return self


class ProvenanceCoverageSummary(StrictModel):
    repository_profile_label: str
    repository_path: str
    scope: str
    evidence_entity_count: int
    authoritative_count: int
    derived_count: int
    heuristic_count: int
    authoritative_ratio: float
    derived_ratio: float
    heuristic_ratio: float
    deterministic_action_capability_count: int
    deterministic_action_capability_total: int
    deterministic_action_capability_ratio: float
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("repository_profile_label", "repository_path", "scope")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_values(self) -> "ProvenanceCoverageSummary":
        if any(
            value < 0
            for value in (
                self.evidence_entity_count,
                self.authoritative_count,
                self.derived_count,
                self.heuristic_count,
                self.deterministic_action_capability_count,
                self.deterministic_action_capability_total,
            )
        ):
            raise ValueError("coverage counts must be >= 0")
        if self.authoritative_count + self.derived_count + self.heuristic_count != self.evidence_entity_count:
            raise ValueError("provenance counts are inconsistent")
        if self.evidence_entity_count == 0:
            if any(value != 0.0 for value in (self.authoritative_ratio, self.derived_ratio, self.heuristic_ratio)):
                raise ValueError("empty evidence set must have zero provenance ratios")
        for value in (
            self.authoritative_ratio,
            self.derived_ratio,
            self.heuristic_ratio,
            self.deterministic_action_capability_ratio,
        ):
            if value < 0.0 or value > 1.0:
                raise ValueError("coverage ratios must be between 0.0 and 1.0")
        if self.deterministic_action_capability_total <= 0:
            raise ValueError("deterministic_action_capability_total must be > 0")
        if self.deterministic_action_capability_count > self.deterministic_action_capability_total:
            raise ValueError("deterministic_action_capability_count exceeds total")
        return self


class HeadlineEfficiencyMetric(StrictModel):
    metric_name: str
    baseline_value: str
    suitcode_value: str
    interpretation: str
    is_hero_metric: bool = False

    @field_validator("metric_name", "baseline_value", "suitcode_value", "interpretation")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class TaskFailureExplanation(StrictModel):
    task_id: str
    suite_role: SuiteRole
    arm: EvaluationArm
    task_family: str
    task_taxonomy: TaskTaxonomy
    ground_truth_kind: GroundTruthKind
    expected_success_criteria: tuple[str, ...]
    run_temperature: RunTemperature
    repository_profile_label: str
    repository_path: str
    question: str
    selector_summary: str | None = None
    status: EvaluationStatus
    failure_kind: EvaluationFailureKind | None = None
    failure_summary: str | None = None
    plain_language_explanation: str
    is_infrastructure_failure: bool
    is_scoring_failure: bool
    is_answer_failure: bool
    transcript_tokens: int | None = None
    turn_count: int | None = None
    duration_ms: int
    expected_answer: dict[str, object] = Field(default_factory=dict)
    actual_answer: dict[str, object] | None = None
    field_value_differences: dict[str, dict[str, object]] = Field(default_factory=dict)
    report_id: str
    stdout_jsonl_path: str
    rollout_artifact_path: str | None = None
    output_last_message_path: str

    @field_validator(
        "task_id",
        "task_family",
        "repository_profile_label",
        "repository_path",
        "question",
        "plain_language_explanation",
        "report_id",
        "stdout_jsonl_path",
        "output_last_message_path",
        "selector_summary",
        "failure_summary",
        "rollout_artifact_path",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_failure_shape(self) -> "TaskFailureExplanation":
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.transcript_tokens is not None and self.transcript_tokens < 0:
            raise ValueError("transcript_tokens must be >= 0")
        if self.turn_count is not None and self.turn_count < 0:
            raise ValueError("turn_count must be >= 0")
        if not self.expected_answer:
            raise ValueError("expected_answer must not be empty")
        if not self.expected_success_criteria:
            raise ValueError("expected_success_criteria must not be empty")
        if self.status == EvaluationStatus.PASSED and (self.failure_kind is not None or self.failure_summary is not None):
            raise ValueError("passed task explanations must not carry failure metadata")
        if self.status != EvaluationStatus.PASSED and (self.failure_kind is None or self.failure_summary is None):
            raise ValueError("failed/error task explanations must include failure metadata")
        return self


class SuiteFailureExplanation(StrictModel):
    suite_role: SuiteRole
    arm: EvaluationArm
    task_total: int
    task_passed: int
    task_failed: int
    task_error: int
    failure_kind_mix: dict[str, int]
    plain_language_summary: str
    interpretation_notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("plain_language_summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("plain_language_summary must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_counts(self) -> "SuiteFailureExplanation":
        if any(value < 0 for value in (self.task_total, self.task_passed, self.task_failed, self.task_error)):
            raise ValueError("suite failure explanation counts must be >= 0")
        if self.task_passed + self.task_failed + self.task_error != self.task_total:
            raise ValueError("suite failure explanation counts are inconsistent")
        return self


class CodexStandoutComparisonSpec(StrictModel):
    stable_readonly_tasks_file: str
    calibration_tasks_file: str | None = None
    stable_execution_tasks_file: str
    stress_readonly_tasks_file: str
    passive_repository_root: str = "."
    include_stable_execution: bool = True
    include_stress_readonly: bool = True
    include_passive_usage_summary: bool = True
    stable_timeout_seconds: int | None = None
    stress_timeout_seconds: int | None = None

    @field_validator(
        "stable_readonly_tasks_file",
        "calibration_tasks_file",
        "stable_execution_tasks_file",
        "stress_readonly_tasks_file",
        "passive_repository_root",
    )
    @classmethod
    def _validate_task_file(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("task file path must not be empty")
        return stripped

    @field_validator("stable_timeout_seconds", "stress_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("timeout overrides must be > 0")
        return value


class CodexStandoutReport(StrictModel):
    report_id: str
    generated_at_utc: str
    model: str | None = None
    stable_readonly_suitcode: ArmRunReference
    stable_readonly_baseline: ArmRunReference
    stable_readonly_suitcode_metadata: AgentRunMetadata | None = None
    stable_readonly_baseline_metadata: AgentRunMetadata | None = None
    calibration_suitcode: ArmRunReference | None = None
    calibration_baseline: ArmRunReference | None = None
    calibration_suitcode_metadata: AgentRunMetadata | None = None
    calibration_baseline_metadata: AgentRunMetadata | None = None
    stable_execution_suitcode: ArmRunReference | None = None
    stable_execution_baseline: ArmRunReference | None = None
    stable_execution_suitcode_metadata: AgentRunMetadata | None = None
    stable_execution_baseline_metadata: AgentRunMetadata | None = None
    stress_readonly_suitcode: ArmRunReference | None = None
    stress_readonly_baseline: ArmRunReference | None = None
    stress_readonly_suitcode_metadata: AgentRunMetadata | None = None
    stress_readonly_baseline_metadata: AgentRunMetadata | None = None
    evaluation_scope: dict[str, object]
    protocol: BenchmarkProtocol
    measured_metrics: tuple[MetricDefinition, ...]
    estimated_metrics: tuple[MetricDefinition, ...]
    derived_metrics: tuple[MetricDefinition, ...]
    headline_deltas: tuple[ComparisonDelta, ...]
    stable_readonly_summary: dict[str, object]
    stable_execution_summary: dict[str, object] | None = None
    stress_summary: dict[str, object] | None = None
    stress_baseline_summary: dict[str, object] | None = None
    passive_usage_summary: dict[str, object] | None = None
    headline_efficiency: tuple[HeadlineEfficiencyMetric, ...] = Field(default_factory=tuple)
    provenance_coverage: tuple[ProvenanceCoverageSummary, ...] = Field(default_factory=tuple)
    figures: tuple[ComparisonFigure, ...] = Field(default_factory=tuple)
    terminology: tuple[TerminologyEntry, ...] = Field(default_factory=tuple)
    suite_descriptions: tuple[SuiteDescription, ...] = Field(default_factory=tuple)
    arm_policies: tuple[ArmPolicyDescription, ...] = Field(default_factory=tuple)
    suite_failure_explanations: tuple[SuiteFailureExplanation, ...] = Field(default_factory=tuple)
    task_level_summaries: tuple[TaskFailureExplanation, ...] = Field(default_factory=tuple)
    evaluation_validity_notes: tuple[str, ...] = Field(default_factory=tuple)
    methodology: dict[str, object]
    limitations: tuple[str, ...] = Field(default_factory=tuple)
    repro_commands: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("report_id", "generated_at_utc")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _validate_sections(self) -> "CodexStandoutReport":
        if not self.headline_deltas:
            raise ValueError("headline_deltas must not be empty")
        if not self.evaluation_scope:
            raise ValueError("evaluation_scope must not be empty")
        if not self.methodology:
            raise ValueError("methodology must not be empty")
        if not self.repro_commands:
            raise ValueError("repro_commands must not be empty")
        if not self.measured_metrics:
            raise ValueError("measured_metrics must not be empty")
        if not self.estimated_metrics:
            raise ValueError("estimated_metrics must not be empty")
        if not self.derived_metrics:
            raise ValueError("derived_metrics must not be empty")
        if not self.suite_descriptions:
            raise ValueError("suite_descriptions must not be empty")
        if not self.arm_policies:
            raise ValueError("arm_policies must not be empty")
        if not self.terminology:
            raise ValueError("terminology must not be empty")
        if not self.evaluation_validity_notes:
            raise ValueError("evaluation_validity_notes must not be empty")
        if not self.headline_efficiency:
            raise ValueError("headline_efficiency must not be empty")
        if not self.provenance_coverage:
            raise ValueError("provenance_coverage must not be empty")
        return self
