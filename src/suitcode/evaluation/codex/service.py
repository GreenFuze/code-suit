from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from suitcode.analytics.codex_session_parser import CodexSessionParser
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.correlation import AnalyticsCorrelationService
from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.output_schemas import model_for_family, schema_for_family
from suitcode.evaluation.codex.prompts import CodexPromptLibrary
from suitcode.evaluation.codex.task_contracts import contract_for
from suitcode.evaluation.codex.runner import CodexCliRunner, CodexRunArtifacts, CodexRunStatus
from suitcode.evaluation.codex.scoring import CodexEvaluationScorer
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily
from suitcode.evaluation.models import (
    ActionScore,
    AnswerScore,
    CodexEvaluationReport,
    CodexEvaluationTaskResult,
    EvaluationFailureKind,
    EvaluationStatus,
    RequiredToolTrace,
    ToolSelectionScore,
)
from suitcode.evaluation.reporting import CodexEvaluationReporter


@dataclass(frozen=True)
class _BaselineExpectation:
    expected_answer: dict[str, object]
    expected_argument_subsets: tuple[tuple[str, dict[str, object]], ...]
    required_action_kind: str | None = None
    required_action_target_id: str | None = None
    expected_action_status: str | None = None


@dataclass(frozen=True)
class _TaskAttempt:
    attempt_number: int
    run: CodexRunArtifacts
    session: object | None
    actual_answer: dict[str, object] | None
    schema_valid: bool
    answer_notes: tuple[str, ...]
    notes: tuple[str, ...]
    tool_selection: ToolSelectionScore
    argument_scores: tuple
    answer_score: AnswerScore
    action_score: ActionScore
    required_tool_traces: tuple[RequiredToolTrace, ...]
    used_suitcode_tool_count: int | None
    used_high_value_tool_count: int | None
    first_suitcode_tool_index: int | None
    first_high_value_tool_index: int | None
    turn_count: int | None
    correlation_quality: str | None
    session_id: str | None
    token_breakdown: object | None
    status: EvaluationStatus
    failure_kind: EvaluationFailureKind | None
    failure_summary: str | None


class CodexEvaluationService:
    def __init__(
        self,
        *,
        working_directory: Path | None = None,
        runner: CodexCliRunner | None = None,
        prompt_library: CodexPromptLibrary | None = None,
        scorer: CodexEvaluationScorer | None = None,
        reporter: CodexEvaluationReporter | None = None,
        service_factory=None,
        analytics_settings: AnalyticsSettings | None = None,
        parser: CodexSessionParser | None = None,
        capture_builder: CodexTranscriptCaptureBuilder | None = None,
        token_estimator: TranscriptTokenEstimator | None = None,
    ) -> None:
        self._working_directory = (working_directory or Path.cwd()).expanduser().resolve()
        self._analytics_settings = analytics_settings or AnalyticsSettings.from_env()
        self._analytics_store = JsonlAnalyticsStore(self._analytics_settings)
        self._runner = runner or CodexCliRunner()
        self._prompt_library = prompt_library or CodexPromptLibrary()
        self._scorer = scorer or CodexEvaluationScorer()
        self._reporter = reporter or CodexEvaluationReporter(self._working_directory / ".suit" / "evaluation" / "codex" / "runs")
        self._service_factory = service_factory or self._default_service_factory
        self._parser = parser or CodexSessionParser()
        self._capture_builder = capture_builder or CodexTranscriptCaptureBuilder()
        self._token_estimator = token_estimator or TranscriptTokenEstimator()
        self._correlation = AnalyticsCorrelationService(JsonlAnalyticsStore(self._analytics_settings))

    def load_tasks(self, tasks_file: Path) -> tuple[CodexEvaluationTask, ...]:
        import json

        payload = json.loads(tasks_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Codex evaluation tasks file must contain a JSON list")
        return tuple(CodexEvaluationTask.model_validate(item) for item in payload)

    def run(
        self,
        tasks: tuple[CodexEvaluationTask, ...],
        *,
        model: str | None = None,
        profile: str | None = None,
        prompt_arm: EvaluationArm = EvaluationArm.SUITCODE,
        config_overrides: tuple[str, ...] = (),
        full_auto: bool = True,
        sandbox: str = "workspace-write",
        bypass_approvals_and_sandbox: bool = False,
    ) -> CodexEvaluationReport:
        report_id = f"codex-eval-{uuid4().hex}"
        task_metadata: dict[str, dict[str, object]] = {}
        results_list: list[CodexEvaluationTaskResult] = []
        for task in tasks:
            try:
                result = self.run_task(
                    task,
                    report_id=report_id,
                    model=model,
                    profile=profile,
                    prompt_arm=prompt_arm,
                    config_overrides=config_overrides,
                    full_auto=full_auto,
                    sandbox=sandbox,
                    bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
                    task_metadata=task_metadata,
                )
            except Exception as exc:  # noqa: BLE001
                result = self._error_result(
                    task,
                    report_id=report_id,
                    failure_kind=EvaluationFailureKind.UNEXPECTED_EXCEPTION,
                    summary=f"{exc.__class__.__name__}: {exc}",
                )
                task_metadata[task.task_id] = {
                    "task": task.model_dump(mode="json"),
                    "notes": [f"{exc.__class__.__name__}: {exc}"],
                    "failure_kind": EvaluationFailureKind.UNEXPECTED_EXCEPTION.value,
                }
            results_list.append(result)
        results = tuple(results_list)
        report = self._build_report(report_id=report_id, results=results)
        self._reporter.write_report(report, task_metadata=task_metadata)
        return report

    def run_task(
        self,
        task: CodexEvaluationTask,
        *,
        report_id: str,
        model: str | None,
        profile: str | None,
        prompt_arm: EvaluationArm,
        config_overrides: tuple[str, ...],
        full_auto: bool,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
        task_metadata: dict[str, dict[str, object]],
    ) -> CodexEvaluationTaskResult:
        repository_root = (self._working_directory / task.repository_path).expanduser().resolve()
        if not repository_root.exists():
            raise ValueError(f"repository path not found for task `{task.task_id}`: `{repository_root}`")
        task_dir = self._reporter.runs_root / report_id / "tasks" / task.task_id
        baseline = self._build_baseline(task, repository_root=repository_root)
        prompt_text = self._prompt_library.build_prompt(task, repository_root=repository_root, arm=prompt_arm)
        attempts = [
            self._execute_attempt(
                task=task,
                baseline=baseline,
                repository_root=repository_root,
                prompt_text=prompt_text,
                model=model,
                profile=profile,
                config_overrides=config_overrides,
                full_auto=full_auto,
                sandbox=sandbox,
                bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
                output_directory=task_dir / "attempt-1",
                attempt_number=1,
            )
        ]
        if self._should_retry_attempt(attempts[0]):
            attempts.append(
                self._execute_attempt(
                    task=task,
                    baseline=baseline,
                    repository_root=repository_root,
                    prompt_text=prompt_text,
                    model=model,
                    profile=profile,
                    config_overrides=config_overrides,
                    full_auto=full_auto,
                    sandbox=sandbox,
                    bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
                    output_directory=task_dir / "attempt-2",
                    attempt_number=2,
                )
            )

        final_attempt = attempts[-1]
        combined_notes: list[str] = []
        for attempt in attempts:
            for note in attempt.notes:
                prefixed = f"attempt {attempt.attempt_number}: {note}"
                if prefixed not in combined_notes:
                    combined_notes.append(prefixed)
        if final_attempt.failure_summary is not None:
            final_failure_note = f"attempt {final_attempt.attempt_number}: {final_attempt.failure_summary}"
            if final_failure_note not in combined_notes:
                combined_notes.insert(0, final_failure_note)
        all_required_tool_traces = tuple(trace for attempt in attempts for trace in attempt.required_tool_traces)
        task_metadata[task.task_id] = {
            "task": task.model_dump(mode="json"),
            "baseline": baseline.expected_answer,
            "failure_kind": (final_attempt.failure_kind.value if final_attempt.failure_kind is not None else None),
            "notes": combined_notes,
            "required_tool_traces": [trace.model_dump(mode="json") for trace in all_required_tool_traces],
            "attempts": [
                {
                    "attempt_number": attempt.attempt_number,
                    "status": attempt.status.value,
                    "failure_kind": (attempt.failure_kind.value if attempt.failure_kind is not None else None),
                    "failure_summary": attempt.failure_summary,
                    "notes": list(attempt.notes),
                    "stdout_jsonl_path": str(attempt.run.stdout_jsonl_path),
                    "rollout_artifact_path": (str(attempt.run.session_artifact_path) if attempt.run.session_artifact_path is not None else None),
                    "output_last_message_path": str(attempt.run.output_last_message_path),
                }
                for attempt in attempts
            ],
            "stdout_jsonl_path": str(final_attempt.run.stdout_jsonl_path),
            "rollout_artifact_path": (str(final_attempt.run.session_artifact_path) if final_attempt.run.session_artifact_path is not None else None),
        }
        return CodexEvaluationTaskResult(
            task_id=task.task_id,
            task_family=task.task_family.value,
            status=final_attempt.status,
            failure_kind=final_attempt.failure_kind,
            failure_summary=final_attempt.failure_summary,
            session_id=final_attempt.session_id,
            repository_root=str(repository_root),
            duration_ms=sum(attempt.run.duration_ms for attempt in attempts),
            attempt_count=len(attempts),
            attempt_failure_kinds=tuple(
                attempt.failure_kind.value for attempt in attempts[:-1] if attempt.failure_kind is not None
            ),
            infrastructure_retry_applied=(len(attempts) > 1),
            turn_count=final_attempt.turn_count,
            required_tool_count=len(task.expected_required_tools),
            used_suitcode_tool_count=final_attempt.used_suitcode_tool_count,
            used_high_value_tool_count=final_attempt.used_high_value_tool_count,
            first_suitcode_tool_index=final_attempt.first_suitcode_tool_index,
            first_high_value_tool_index=final_attempt.first_high_value_tool_index,
            tool_selection=final_attempt.tool_selection,
            argument_scores=final_attempt.argument_scores,
            answer_score=final_attempt.answer_score,
            action_score=final_attempt.action_score,
            required_tool_traces=all_required_tool_traces,
            transcript_token_breakdown=final_attempt.token_breakdown,
            correlation_quality=final_attempt.correlation_quality,
            stdout_jsonl_path=str(final_attempt.run.stdout_jsonl_path),
            rollout_artifact_path=(str(final_attempt.run.session_artifact_path) if final_attempt.run.session_artifact_path is not None else None),
            output_last_message_path=str(final_attempt.run.output_last_message_path),
            notes=tuple(combined_notes),
        )

    def _execute_attempt(
        self,
        *,
        task: CodexEvaluationTask,
        baseline: _BaselineExpectation,
        repository_root: Path,
        prompt_text: str,
        model: str | None,
        profile: str | None,
        config_overrides: tuple[str, ...],
        full_auto: bool,
        sandbox: str,
        bypass_approvals_and_sandbox: bool,
        output_directory: Path,
        attempt_number: int,
    ) -> _TaskAttempt:
        run = self._runner.run(
            repository_root=repository_root,
            prompt_text=prompt_text,
            output_schema=schema_for_family(task.task_family),
            output_directory=output_directory,
            timeout_seconds=task.timeout_seconds,
            model=model,
            profile=profile,
            config_overrides=config_overrides,
            full_auto=full_auto,
            sandbox=sandbox,
            bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
        )

        notes: list[str] = []
        if run.failure_summary:
            notes.append(run.failure_summary)
        if run.stderr_excerpt:
            notes.append(f"stderr: {run.stderr_excerpt}")

        session = None
        if run.session_artifact_path is not None and not run.session_artifact_ambiguous:
            session = self._parser.parse(run.session_artifact_path)
            session = self._correlation.correlate_codex_session(session, repository_root)
            session = session.model_copy(update={"transcript_capture": self._capture_builder.build(run.session_artifact_path)})
            session = self._token_estimator.estimate_codex_session(session)

        actual_answer, schema_valid, answer_notes = self._load_final_answer(task, run.output_last_message_path)
        notes.extend(answer_notes)

        if session is None:
            tool_selection = ToolSelectionScore(
                required_tools_present=False,
                required_tool_names=task.expected_required_tools,
                used_tool_names=(),
                missing_required_tools=task.expected_required_tools,
            )
            argument_scores = ()
            action_score = ActionScore(
                required_action_kind=baseline.required_action_kind,
                required_action_target_id=baseline.required_action_target_id,
                executed=False,
                matched_target=False,
                status=baseline.expected_action_status,
            )
            used_suitcode_tool_count = None
            used_high_value_tool_count = None
            first_suitcode_tool_index = None
            first_high_value_tool_index = None
            turn_count = None
            correlation_quality = None
            session_id = None
            token_breakdown = None
        else:
            tool_selection = self._scorer.tool_selection_score(session, required_tools=task.expected_required_tools)
            argument_scores = self._scorer.argument_scores(session, expected_argument_subsets=baseline.expected_argument_subsets)
            action_score = self._scorer.action_score(
                session,
                required_action_kind=baseline.required_action_kind,
                required_action_target_id=baseline.required_action_target_id,
                expected_status=baseline.expected_action_status,
            )
            used_suitcode_tool_count = sum(item.call_count for item in session.suitcode_tools)
            used_high_value_tool_count = sum(item.call_count for item in session.suitcode_tools if item.tool_name in HIGH_VALUE_TOOL_SET)
            first_suitcode_tool_index = session.first_suitcode_tool_index
            first_high_value_tool_index = session.first_high_value_suitcode_tool_index
            turn_count = session.transcript_metrics.tool_event_count
            correlation_quality = session.correlation_quality.value
            session_id = session.session_id
            token_breakdown = session.token_breakdown

        required_tool_traces = self._required_tool_traces(
            session=session,
            required_tools=task.expected_required_tools,
            repository_root=repository_root,
            attempt_number=attempt_number,
        )

        answer_score = self._scorer.answer_score(
            actual_answer=actual_answer,
            expected_answer=baseline.expected_answer,
            schema_valid=schema_valid,
        )
        status, failure_kind, failure_summary = self._classify_result(
            run=run,
            session=session,
            tool_selection=tool_selection,
            argument_scores=argument_scores,
            answer_score=answer_score,
            action_score=action_score,
            required_action=baseline.required_action_kind is not None,
            answer_notes=answer_notes,
        )
        if failure_summary is not None and failure_summary not in notes:
            notes.insert(0, failure_summary)
        return _TaskAttempt(
            attempt_number=attempt_number,
            run=run,
            session=session,
            actual_answer=actual_answer,
            schema_valid=schema_valid,
            answer_notes=answer_notes,
            notes=tuple(notes),
            tool_selection=tool_selection,
            argument_scores=argument_scores,
            answer_score=answer_score,
            action_score=action_score,
            required_tool_traces=required_tool_traces,
            used_suitcode_tool_count=used_suitcode_tool_count,
            used_high_value_tool_count=used_high_value_tool_count,
            first_suitcode_tool_index=first_suitcode_tool_index,
            first_high_value_tool_index=first_high_value_tool_index,
            turn_count=turn_count,
            correlation_quality=correlation_quality,
            session_id=session_id,
            token_breakdown=token_breakdown,
            status=status,
            failure_kind=failure_kind,
            failure_summary=failure_summary,
        )

    @staticmethod
    def _should_retry_attempt(attempt: _TaskAttempt) -> bool:
        infrastructure_failures = {
            EvaluationFailureKind.CLI_ERROR,
            EvaluationFailureKind.USAGE_LIMIT,
            EvaluationFailureKind.SESSION_ARTIFACT_MISSING,
            EvaluationFailureKind.SESSION_CORRELATION_AMBIGUOUS,
        }
        if attempt.failure_kind in infrastructure_failures:
            if attempt.failure_kind == EvaluationFailureKind.USAGE_LIMIT:
                return False
            if attempt.failure_kind in {
                EvaluationFailureKind.SESSION_ARTIFACT_MISSING,
                EvaluationFailureKind.SESSION_CORRELATION_AMBIGUOUS,
            }:
                return True
            if attempt.used_suitcode_tool_count not in (None, 0):
                return False
            if attempt.schema_valid or attempt.actual_answer is not None:
                return False
            return True
        if attempt.failure_kind not in {
            EvaluationFailureKind.REQUIRED_TOOLS_MISSING,
            EvaluationFailureKind.ANSWER_MISMATCH,
            EvaluationFailureKind.SCHEMA_VALIDATION_FAILED,
        }:
            return False
        return any(
            trace.called and (trace.timed_out or trace.error_excerpt is not None)
            for trace in attempt.required_tool_traces
        )

    def load_report(self, report_id: str) -> CodexEvaluationReport:
        return self._reporter.load_report(report_id)

    def load_latest_report(self) -> CodexEvaluationReport | None:
        return self._reporter.load_latest_report()

    @staticmethod
    def _default_service_factory():
        from suitcode.mcp.service import SuitMcpService
        from suitcode.mcp.state import WorkspaceRegistry

        return SuitMcpService(registry=WorkspaceRegistry())

    def _build_baseline(self, task: CodexEvaluationTask, *, repository_root: Path) -> _BaselineExpectation:
        service = self._service_factory()
        opened = service.open_workspace(str(repository_root))
        workspace_id = opened.workspace.workspace_id
        repository_id = opened.initial_repository.repository_id
        contract = contract_for(task.task_family)
        try:
            if task.task_family == CodexTaskFamily.ORIENTATION:
                summary = service.repository_summary(workspace_id, repository_id, preview_limit=8)
                truth = service.get_truth_coverage(workspace_id, repository_id)
                return _BaselineExpectation(
                    expected_answer={
                        "workspace_id": workspace_id,
                        "repository_id": repository_id,
                        "provider_ids": list(summary.provider_ids),
                        "component_count": summary.component_count,
                        "test_count": summary.test_count,
                        "quality_provider_count": len(summary.quality_provider_ids),
                        "overall_truth_availability": truth.overall_availability,
                    },
                    expected_argument_subsets=contract.expected_argument_subsets(task, workspace_id=workspace_id, repository_id=repository_id),
                )
            if task.task_family == CodexTaskFamily.CHANGE_ANALYSIS:
                selector = dict(task.target_selector)
                impact = service.analyze_change(workspace_id, repository_id, **selector)
                return _BaselineExpectation(
                    expected_answer={
                        "target_kind": impact.target_kind,
                        "owner_id": impact.owner.id,
                        "primary_component_id": (impact.primary_component.id if impact.primary_component is not None else None),
                        "related_test_ids": sorted(item.test.id for item in impact.related_tests),
                        "quality_gate_provider_ids": sorted(item.provider_id for item in impact.quality_gates),
                        "evidence_edge_count": impact.evidence.total_edges,
                        "overall_truth_availability": impact.truth_coverage.overall_availability,
                    },
                    expected_argument_subsets=contract.expected_argument_subsets(task, workspace_id=workspace_id, repository_id=repository_id),
                )
            if task.task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
                selector = dict(task.target_selector)
                change_set = service.get_minimum_verified_change_set(workspace_id, repository_id, **selector)
                return _BaselineExpectation(
                    expected_answer={
                        "owner_id": change_set.owner.id,
                        "primary_component_id": (change_set.primary_component.id if change_set.primary_component is not None else None),
                        "test_target_ids": sorted(item.test_id for item in change_set.tests),
                        "build_target_ids": sorted(item.action_id for item in change_set.build_targets),
                        "runner_action_ids": sorted(item.action_id for item in change_set.runner_actions),
                        "quality_validation_operation_ids": sorted(item.id for item in change_set.quality_validation_operations),
                        "quality_hygiene_operation_ids": sorted(item.id for item in change_set.quality_hygiene_operations),
                    },
                    expected_argument_subsets=contract.expected_argument_subsets(task, workspace_id=workspace_id, repository_id=repository_id),
                )
            if task.task_family == CodexTaskFamily.TRUTH_COVERAGE:
                truth = service.get_truth_coverage(workspace_id, repository_id)
                return _BaselineExpectation(
                    expected_answer={
                        "overall_availability": truth.overall_availability,
                        **{
                            domain.domain: {
                                "availability": domain.availability,
                                "authoritative_count": domain.authoritative_count,
                                "derived_count": domain.derived_count,
                                "heuristic_count": domain.heuristic_count,
                                "unavailable_count": domain.unavailable_count,
                            }
                            for domain in truth.domains
                        },
                    },
                    expected_argument_subsets=contract.expected_argument_subsets(task, workspace_id=workspace_id, repository_id=repository_id),
                )
            if task.task_family == CodexTaskFamily.TEST_EXECUTION:
                explicit_test_id = task.target_selector.get("test_id")
                if explicit_test_id is None:
                    tests = service.list_tests(workspace_id, repository_id, limit=200, offset=0)
                    if not tests.items:
                        raise ValueError("no discovered tests available for test_execution baseline")
                    test_id = tests.items[0].id
                else:
                    test_id = explicit_test_id
                description = service.describe_test_target(workspace_id, repository_id, test_id)
                run = service.run_test_targets(workspace_id, repository_id, test_ids=(test_id,), timeout_seconds=task.timeout_seconds)
                execution_status = "passed" if (run.failed == 0 and run.errors == 0 and run.timeouts == 0) else "failed"
                return _BaselineExpectation(
                    expected_answer={
                        "selected_test_id": test_id,
                        "command_preview": list(description.command_argv),
                        "execution_status": execution_status,
                        "passed": run.passed,
                        "failed": run.failed,
                        "errors": run.errors,
                        "timeouts": run.timeouts,
                    },
                    expected_argument_subsets=(
                        ("describe_test_target", {"workspace_id": workspace_id, "repository_id": repository_id, "test_id": test_id}),
                        ("run_test_targets", {"workspace_id": workspace_id, "repository_id": repository_id, "test_ids": (test_id,)}),
                    ),
                    required_action_kind="test",
                    required_action_target_id=test_id,
                    expected_action_status=execution_status,
                )
            if task.task_family == CodexTaskFamily.BUILD_EXECUTION:
                explicit_action_id = task.target_selector.get("action_id")
                if explicit_action_id is None:
                    builds = service.list_build_targets(workspace_id, repository_id, limit=200, offset=0)
                    if not builds.items:
                        raise ValueError("no deterministic build targets available for build_execution baseline")
                    action_id = builds.items[0].action_id
                else:
                    action_id = explicit_action_id
                description = service.describe_build_target(workspace_id, repository_id, action_id)
                result = service.build_target(workspace_id, repository_id, action_id, timeout_seconds=task.timeout_seconds)
                execution_status = "passed" if result.success else "failed"
                return _BaselineExpectation(
                    expected_answer={
                        "selected_action_id": action_id,
                        "command_preview": list(description.invocation.argv),
                        "execution_status": execution_status,
                        "succeeded": result.success,
                    },
                    expected_argument_subsets=(
                        ("describe_build_target", {"workspace_id": workspace_id, "repository_id": repository_id, "action_id": action_id}),
                        ("build_target", {"workspace_id": workspace_id, "repository_id": repository_id, "action_id": action_id}),
                    ),
                    required_action_kind="build",
                    required_action_target_id=action_id,
                    expected_action_status=execution_status,
                )
            raise ValueError(f"unsupported Codex task family `{task.task_family.value}`")
        finally:
            try:
                service.close_workspace(workspace_id)
            except Exception:  # noqa: BLE001
                pass

    def _load_final_answer(self, task: CodexEvaluationTask, path: Path) -> tuple[dict[str, object] | None, bool, tuple[str, ...]]:
        if not path.exists():
            return None, False, (f"final answer file missing: `{path}`",)
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None, False, ("final answer file is empty",)
        model_cls = model_for_family(task.task_family)
        try:
            validated = model_cls.model_validate_json(raw)
        except ValidationError as exc:
            return None, False, (f"final answer schema validation failed: {exc}",)
        return validated.model_dump(mode="json"), True, ()

    def _build_report(self, *, report_id: str, results: tuple[CodexEvaluationTaskResult, ...]) -> CodexEvaluationReport:
        task_total = len(results)
        task_passed = sum(1 for item in results if item.status == EvaluationStatus.PASSED)
        task_failed = sum(1 for item in results if item.status == EvaluationStatus.FAILED)
        task_error = sum(1 for item in results if item.status == EvaluationStatus.ERROR)
        correlation_quality_mix = Counter(item.correlation_quality for item in results if item.correlation_quality is not None)
        failure_kind_mix = Counter(item.failure_kind.value for item in results if item.failure_kind is not None)
        infrastructure_failure_kind_mix = Counter(
            item.failure_kind.value
            for item in results
            if item.failure_kind in {
                EvaluationFailureKind.CLI_ERROR,
                EvaluationFailureKind.USAGE_LIMIT,
                EvaluationFailureKind.SESSION_ARTIFACT_MISSING,
                EvaluationFailureKind.SESSION_CORRELATION_AMBIGUOUS,
            }
        )
        required_tool_timeout_mix: Counter[str] = Counter()
        required_tool_failure_mix: Counter[str] = Counter()
        for item in results:
            for trace in item.required_tool_traces:
                if trace.timed_out:
                    required_tool_timeout_mix[trace.tool_name] += 1
                elif not trace.success:
                    required_tool_failure_mix[trace.tool_name] += 1
        token_breakdowns = [item.transcript_token_breakdown for item in results if item.transcript_token_breakdown is not None]
        applicable_actions = [item for item in results if item.action_score.required_action_kind is not None]
        first_suitcode_tool_indices = [item.first_suitcode_tool_index for item in results if item.first_suitcode_tool_index is not None]
        first_high_value_tool_indices = [item.first_high_value_tool_index for item in results if item.first_high_value_tool_index is not None]
        token_before_first_suitcode = [item.tokens_before_first_suitcode_tool for item in token_breakdowns if item.tokens_before_first_suitcode_tool is not None]
        token_before_first_high_value = [item.tokens_before_first_high_value_suitcode_tool for item in token_breakdowns if item.tokens_before_first_high_value_suitcode_tool is not None]
        artifact_available = sum(1 for item in results if item.rollout_artifact_path is not None)
        no_high_value_sessions = sum(1 for item in results if item.used_high_value_tool_count == 0)
        retried_task_count = sum(1 for item in results if item.infrastructure_retry_applied)
        post_retry_pass_count = sum(1 for item in results if item.infrastructure_retry_applied and item.status == EvaluationStatus.PASSED)
        return CodexEvaluationReport(
            report_id=report_id,
            generated_at_utc=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            task_total=task_total,
            task_passed=task_passed,
            task_failed=task_failed,
            task_error=task_error,
            avg_duration_ms=(sum(item.duration_ms for item in results) / task_total if task_total else 0.0),
            avg_transcript_tokens=(sum(item.total_tokens for item in token_breakdowns) / len(token_breakdowns) if token_breakdowns else None),
            avg_tokens_before_first_suitcode_tool=(sum(token_before_first_suitcode) / len(token_before_first_suitcode) if token_before_first_suitcode else None),
            avg_tokens_before_first_high_value_tool=(sum(token_before_first_high_value) / len(token_before_first_high_value) if token_before_first_high_value else None),
            required_tool_success_rate=(sum(1 for item in results if item.tool_selection.required_tools_present) / task_total if task_total else 0.0),
            high_value_tool_early_rate=(sum(1 for item in results if item.tool_selection.used_high_value_tool_early) / task_total if task_total else 0.0),
            answer_schema_success_rate=(sum(1 for item in results if item.answer_score.schema_valid) / task_total if task_total else 0.0),
            deterministic_action_success_rate=(
                sum(1 for item in applicable_actions if item.action_score.executed and item.action_score.matched_target and item.action_score.status == "passed")
                / len(applicable_actions)
                if applicable_actions
                else 0.0
            ),
            timeout_rate=(sum(1 for item in results if item.failure_kind == EvaluationFailureKind.TIMEOUT) / task_total if task_total else 0.0),
            session_artifact_resolution_rate=(artifact_available / task_total if task_total else 0.0),
            retry_rate=(retried_task_count / task_total if task_total else 0.0),
            retried_task_count=retried_task_count,
            post_retry_pass_count=post_retry_pass_count,
            avg_first_suitcode_tool_index=(sum(first_suitcode_tool_indices) / len(first_suitcode_tool_indices) if first_suitcode_tool_indices else None),
            avg_first_high_value_tool_index=(sum(first_high_value_tool_indices) / len(first_high_value_tool_indices) if first_high_value_tool_indices else None),
            sessions_with_no_high_value_tool_rate=(no_high_value_sessions / task_total if task_total else 0.0),
            failure_kind_mix=dict(failure_kind_mix),
            infrastructure_failure_kind_mix=dict(infrastructure_failure_kind_mix),
            required_tool_timeout_mix=dict(required_tool_timeout_mix),
            required_tool_failure_mix=dict(required_tool_failure_mix),
            correlation_quality_mix=dict(correlation_quality_mix),
            tasks=results,
        )

    @staticmethod
    def _error_result(
        task: CodexEvaluationTask,
        *,
        report_id: str,
        failure_kind: EvaluationFailureKind,
        summary: str,
    ) -> CodexEvaluationTaskResult:
        repository_root = str(Path(task.repository_path))
        return CodexEvaluationTaskResult(
            task_id=task.task_id,
            task_family=task.task_family.value,
            status=EvaluationStatus.ERROR,
            failure_kind=failure_kind,
            failure_summary=summary,
            repository_root=repository_root,
            duration_ms=0,
            required_tool_count=len(task.expected_required_tools),
            tool_selection=ToolSelectionScore(
                required_tools_present=False,
                required_tool_names=task.expected_required_tools,
                used_tool_names=(),
                missing_required_tools=task.expected_required_tools,
            ),
            answer_score=AnswerScore(schema_valid=False),
            action_score=ActionScore(executed=False, matched_target=False),
            stdout_jsonl_path=str(Path(".suit") / "evaluation" / "codex" / "runs" / report_id / "tasks" / task.task_id / "stdout.jsonl"),
            output_last_message_path=str(Path(".suit") / "evaluation" / "codex" / "runs" / report_id / "tasks" / task.task_id / "last_message.txt"),
            notes=(summary,),
        )

    @staticmethod
    def _usage_limit_summary(*, run: CodexRunArtifacts, session: object | None) -> str | None:
        candidates: list[str] = []
        if run.stdout_jsonl_path.exists():
            candidates.append(run.stdout_jsonl_path.read_text(encoding="utf-8", errors="replace"))
        if run.stderr_path.exists():
            candidates.append(run.stderr_path.read_text(encoding="utf-8", errors="replace"))
        if run.session_artifact_path is not None and run.session_artifact_path.exists():
            candidates.append(run.session_artifact_path.read_text(encoding="utf-8", errors="replace"))
        for blob in candidates:
            lowered = blob.lower()
            if "usage limit" not in lowered and "purchase more credits" not in lowered and "\"has_credits\":false" not in lowered:
                continue
            for line in blob.splitlines():
                line_text = line.strip()
                lowered_line = line_text.lower()
                if "usage limit" in lowered_line or "purchase more credits" in lowered_line:
                    return line_text[:400]
            return "Codex usage limit reached before task completion"
        return None

    @staticmethod
    def _classify_result(
        *,
        run: CodexRunArtifacts,
        session: object | None,
        tool_selection: ToolSelectionScore,
        argument_scores,
        answer_score: AnswerScore,
        action_score: ActionScore,
        required_action: bool,
        answer_notes: tuple[str, ...],
    ) -> tuple[EvaluationStatus, EvaluationFailureKind | None, str | None]:
        usage_limit_summary = CodexEvaluationService._usage_limit_summary(run=run, session=session)
        if usage_limit_summary is not None:
            return EvaluationStatus.ERROR, EvaluationFailureKind.USAGE_LIMIT, usage_limit_summary
        if run.status == CodexRunStatus.TIMEOUT:
            return EvaluationStatus.ERROR, EvaluationFailureKind.TIMEOUT, run.failure_summary or "codex exec timed out"
        if run.status == CodexRunStatus.CLI_ERROR:
            return EvaluationStatus.ERROR, EvaluationFailureKind.CLI_ERROR, run.failure_summary or "codex exec failed"
        if run.exit_code not in (None, 0):
            return EvaluationStatus.ERROR, EvaluationFailureKind.CLI_ERROR, run.failure_summary or f"codex exec exited with code {run.exit_code}"
        if run.session_artifact_ambiguous:
            return EvaluationStatus.ERROR, EvaluationFailureKind.SESSION_CORRELATION_AMBIGUOUS, "Codex rollout artifact resolution was ambiguous"
        if run.session_artifact_path is None:
            return EvaluationStatus.ERROR, EvaluationFailureKind.SESSION_ARTIFACT_MISSING, "failed to identify Codex rollout artifact for the run"
        if not answer_score.schema_valid:
            summary = answer_notes[0] if answer_notes else "final answer schema validation failed"
            return EvaluationStatus.FAILED, EvaluationFailureKind.SCHEMA_VALIDATION_FAILED, summary
        if not tool_selection.required_tools_present:
            return EvaluationStatus.FAILED, EvaluationFailureKind.REQUIRED_TOOLS_MISSING, (
                "required SuitCode tools were missing: " + ", ".join(tool_selection.missing_required_tools)
            )
        argument_mismatches = [item for item in argument_scores if not item.matched]
        if argument_mismatches:
            first = argument_mismatches[0]
            mismatch_summary = first.mismatches[0] if first.mismatches else "argument mismatch"
            return EvaluationStatus.FAILED, EvaluationFailureKind.ARGUMENT_MISMATCH, f"{first.tool_name}: {mismatch_summary}"
        if answer_score.missing_fields or answer_score.mismatched_fields:
            details = []
            if answer_score.missing_fields:
                details.append("missing=" + ", ".join(answer_score.missing_fields))
            if answer_score.mismatched_fields:
                details.append("mismatched=" + ", ".join(answer_score.mismatched_fields))
            return EvaluationStatus.FAILED, EvaluationFailureKind.ANSWER_MISMATCH, "; ".join(details)
        if required_action and not action_score.executed:
            return EvaluationStatus.FAILED, EvaluationFailureKind.REQUIRED_ACTION_NOT_EXECUTED, "required deterministic action was not executed"
        if required_action and not action_score.matched_target:
            return EvaluationStatus.FAILED, EvaluationFailureKind.REQUIRED_ACTION_WRONG_TARGET, "deterministic action executed with the wrong target"
        return EvaluationStatus.PASSED, None, None

    def _required_tool_traces(
        self,
        *,
        session,
        required_tools: tuple[str, ...],
        repository_root: Path,
        attempt_number: int,
    ) -> tuple[RequiredToolTrace, ...]:
        if session is None or session.transcript_capture is None:
            return tuple(
                RequiredToolTrace(tool_name=tool_name, attempt_number=attempt_number, called=False, success=False)
                for tool_name in required_tools
            )

        tool_calls = self._scorer.tool_calls(session)
        analytics_events = self._correlated_analytics_events(
            repository_root=repository_root,
            analytics_session_id=session.correlated_analytics_session_id,
        )
        segments = session.transcript_capture.segments
        traces: list[RequiredToolTrace] = []
        for tool_name in required_tools:
            matching_calls = [call for call in tool_calls if call.tool_name == tool_name]
            if not matching_calls:
                traces.append(RequiredToolTrace(tool_name=tool_name, attempt_number=attempt_number, called=False, success=False))
                continue
            matching_call_segments = [
                segment
                for segment in segments
                if segment.kind.value == "mcp_tool_call"
                and segment.is_suitcode
                and segment.canonical_tool_name == tool_name
                and isinstance(segment.metadata, dict)
                and segment.metadata.get("arguments_text") is not None
            ]
            candidates: list[tuple[object, object | None, bool, str | None]] = []
            for index, call in enumerate(matching_calls):
                call_segment = matching_call_segments[index] if index < len(matching_call_segments) else None
                output_segment = None
                if call_segment is not None and isinstance(call_segment.metadata, dict):
                    call_id = call_segment.metadata.get("call_id")
                    output_segment = next(
                        (
                            segment
                            for segment in segments
                            if segment.kind.value == "mcp_tool_output"
                            and isinstance(segment.metadata, dict)
                            and segment.metadata.get("call_id") == call_id
                        ),
                        None,
                    )
                timed_out, error_excerpt = self._tool_output_status(output_segment)
                success = output_segment is not None and not timed_out and error_excerpt is None
                candidates.append((call, call_segment, success, error_excerpt))
            call, call_segment, success, error_excerpt = next(
                (candidate for candidate in reversed(candidates) if candidate[2]),
                candidates[-1],
            )
            analytics_event = analytics_events.get(tool_name)
            if analytics_event is not None and error_excerpt is None:
                error_excerpt = analytics_event.error_message
            traces.append(
                RequiredToolTrace(
                    tool_name=tool_name,
                    attempt_number=attempt_number,
                    call_index=call.call_index,
                    called=True,
                    success=success and error_excerpt is None,
                    error_excerpt=error_excerpt,
                    correlated_duration_ms=(analytics_event.duration_ms if analytics_event is not None else None),
                    timed_out=("timed out" in error_excerpt.lower() if isinstance(error_excerpt, str) else False),
                    arguments_excerpt=self._excerpt(call_segment.metadata.get("arguments_text") if call_segment is not None and isinstance(call_segment.metadata, dict) else None),
                )
            )
        return tuple(traces)

    def _correlated_analytics_events(
        self,
        *,
        repository_root: Path,
        analytics_session_id: str | None,
    ) -> dict[str, object]:
        if analytics_session_id is None:
            return {}
        events = self._analytics_store.load_events(repository_root=repository_root, include_global=True)
        by_tool: dict[str, object] = {}
        for event in events:
            if event.session_id != analytics_session_id:
                continue
            by_tool[event.tool_name] = event
        return by_tool

    @staticmethod
    def _tool_output_status(output_segment) -> tuple[bool, str | None]:
        if output_segment is None or not isinstance(output_segment.metadata, dict):
            return False, "required tool call produced no tool output segment"
        output_text = output_segment.metadata.get("output_text")
        if not isinstance(output_text, str) or not output_text.strip():
            return False, None
        text = output_text.strip()
        timed_out = "timed out" in text.lower()
        try:
            payload = json.loads(text)
        except Exception:  # noqa: BLE001
            return timed_out, text if timed_out else None
        if not isinstance(payload, dict):
            return timed_out, None
        if payload.get("isError") is True:
            structured = payload.get("structuredContent")
            if isinstance(structured, dict):
                err = structured.get("err")
                if isinstance(err, str) and err.strip():
                    return timed_out, err.strip()
            content = payload.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        candidate = item.get("text")
                        if isinstance(candidate, str) and candidate.strip():
                            return timed_out, candidate.strip()
            return timed_out, text
        return timed_out, None

    @staticmethod
    def _excerpt(value: object, *, limit: int = 200) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."
