from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.action_models import ActionKind, ActionQuery, ActionTargetKind, RepositoryAction
from suitcode.core.models import Component, FileInfo, Runner
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, ownership_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_source_kind, preferred_source_tool
from suitcode.core.runner_models import RunnerContext, RunnerExecutionResult, RunnerExecutionStatus
from suitcode.core.tests.models import RelatedTestTarget, ResolvedRelatedTest
from suitcode.core.tests.provenance import is_authoritative_test_provenance
from suitcode.core.validation import validate_preview_limit, validate_timeout_seconds
from suitcode.providers.shared.action_execution import ActionExecutionService, ActionExecutionStatus

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class RunnerService:
    def __init__(self, repository: Repository, action_execution_service: ActionExecutionService | None = None) -> None:
        self._repository = repository
        self._action_execution_service = action_execution_service or ActionExecutionService(
            repository_root=repository.root,
            suit_dir=repository.suit_dir,
        )
        self._runners_by_id: dict[str, Runner] | None = None
        self._components_by_id: dict[str, Component] | None = None

    def describe_runner(
        self,
        runner_id: str,
        file_preview_limit: int = 20,
        test_preview_limit: int = 10,
    ) -> RunnerContext:
        validate_preview_limit(file_preview_limit, "file_preview_limit")
        validate_preview_limit(test_preview_limit, "test_preview_limit")

        runner = self._runner_by_id(runner_id)
        action = self._runner_action_for_id(runner_id)
        primary_component = self._primary_component_for_action(action)
        owned_files = self._repository.list_files_by_owner(runner_id)
        related_tests = self._related_tests_for_runner(primary_component, owned_files)
        return RunnerContext(
            runner=runner,
            action_id=action.id,
            provider_id=action.provider_id,
            invocation=action.invocation,
            primary_component=primary_component,
            owned_file_count=len(owned_files),
            owned_files_preview=owned_files[:file_preview_limit],
            related_test_count=len(related_tests),
            related_tests_preview=related_tests[:test_preview_limit],
            provenance=self._context_provenance(runner, action, owned_files, related_tests),
        )

    def run_runner(self, runner_id: str, timeout_seconds: int = 300) -> RunnerExecutionResult:
        validate_timeout_seconds(timeout_seconds)
        runner = self._runner_by_id(runner_id)
        action = self._runner_action_for_id(runner_id)
        execution = self._action_execution_service.run(
            action_id=action.id,
            command_argv=action.invocation.argv,
            command_cwd=action.invocation.cwd,
            timeout_seconds=timeout_seconds,
            run_group="runners",
        )
        status = self._to_runner_status(execution.status)
        return RunnerExecutionResult(
            runner_id=runner.id,
            action_id=action.id,
            status=status,
            success=status == RunnerExecutionStatus.PASSED,
            command_argv=action.invocation.argv,
            command_cwd=action.invocation.cwd,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            log_path=execution.log_path,
            output_excerpt=execution.output_excerpt,
            provenance=(
                *action.provenance,
                derived_summary_provenance(
                    source_kind=preferred_source_kind(action.provenance),
                    source_tool=preferred_source_tool(action.provenance),
                    evidence_summary="runner execution result derived from deterministic runner action",
                    evidence_paths=(execution.log_path, *merge_provenance_paths(action.provenance, limit=10)),
                ),
            ),
        )

    def _runner_by_id(self, runner_id: str) -> Runner:
        owner = self._repository.resolve_owner(runner_id)
        if owner.kind != "runner":
            raise ValueError(f"owner id is not a runner: `{runner_id}`")
        if self._runners_by_id is None:
            runners: dict[str, Runner] = {}
            for runner in self._repository.arch.get_runners():
                if runner.id in runners:
                    raise ValueError(f"duplicate runner id detected: `{runner.id}`")
                runners[runner.id] = runner
            self._runners_by_id = runners
        try:
            return self._runners_by_id[runner_id]
        except KeyError as exc:
            raise ValueError(f"unknown runner id: `{runner_id}`") from exc

    def _runner_action_for_id(self, runner_id: str) -> RepositoryAction:
        actions = tuple(
            action
            for action in self._repository.list_actions(ActionQuery(runner_id=runner_id))
            if action.kind == ActionKind.RUNNER_EXECUTION
            and action.target_kind == ActionTargetKind.RUNNER
            and action.target_id == runner_id
        )
        if not actions:
            raise ValueError(f"missing runner action for runner id `{runner_id}`")
        if len(actions) != 1:
            raise ValueError(f"ambiguous runner actions for runner id `{runner_id}`")
        return actions[0]

    def _primary_component_for_action(self, action: RepositoryAction) -> Component | None:
        component_owner_ids: list[str] = []
        for owner_id in action.owner_ids:
            owner = self._repository.resolve_owner(owner_id)
            if owner.kind == "component":
                component_owner_ids.append(owner_id)
        unique_ids = sorted(set(component_owner_ids))
        if not unique_ids:
            return None
        if len(unique_ids) > 1:
            raise ValueError(
                f"runner action `{action.id}` maps to multiple components: `{', '.join(unique_ids)}`"
            )

        component_id = unique_ids[0]
        if self._components_by_id is None:
            self._components_by_id = {item.id: item for item in self._repository.arch.get_components()}
        try:
            return self._components_by_id[component_id]
        except KeyError as exc:
            raise ValueError(f"component id could not be resolved: `{component_id}`") from exc

    def _related_tests_for_runner(
        self,
        primary_component: Component | None,
        owned_files: tuple[FileInfo, ...],
    ) -> tuple[ResolvedRelatedTest, ...]:
        if primary_component is not None:
            return self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=primary_component.id))

        by_id: dict[str, ResolvedRelatedTest] = {}
        for file_info in owned_files:
            for related in self._repository.tests.get_related_tests(
                RelatedTestTarget(repository_rel_path=file_info.repository_rel_path)
            ):
                by_id.setdefault(related.test_definition.id, related)
        return tuple(
            sorted(
                by_id.values(),
                key=lambda item: (
                    item.match.test_definition.id,
                    item.match.relation_reason,
                    item.match.matched_owner_id or "",
                    item.match.matched_repository_rel_path or "",
                ),
            )
        )

    def _context_provenance(
        self,
        runner: Runner,
        action: RepositoryAction,
        owned_files: tuple[FileInfo, ...],
        related_tests: tuple[ResolvedRelatedTest, ...],
    ) -> tuple:
        evidence_paths = tuple(item.repository_rel_path for item in owned_files[:10])
        if not evidence_paths:
            evidence_paths = merge_provenance_paths(runner.provenance, limit=10)

        entries = [
            ownership_provenance(
                evidence_summary=f"runner context derived from ownership index for `{runner.id}`",
                evidence_paths=evidence_paths,
            ),
            derived_summary_provenance(
                source_kind=preferred_source_kind(action.provenance),
                source_tool=preferred_source_tool(action.provenance),
                evidence_summary=f"runner invocation derived from deterministic action `{action.id}`",
                evidence_paths=merge_provenance_paths(action.provenance, limit=10),
            ),
        ]
        if related_tests:
            authoritative = all(is_authoritative_test_provenance(item.provenance) for item in related_tests)
            test_provenance = [entry for related in related_tests for entry in related.provenance]
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.TEST_TOOL if authoritative else SourceKind.HEURISTIC,
                    source_tool=preferred_source_tool(test_provenance),
                    evidence_summary="runner-related tests derived from ownership and discovered test metadata",
                    evidence_paths=merge_provenance_paths(test_provenance, limit=10),
                )
            )
        return tuple(entries)

    @staticmethod
    def _to_runner_status(status: ActionExecutionStatus) -> RunnerExecutionStatus:
        if status == ActionExecutionStatus.PASSED:
            return RunnerExecutionStatus.PASSED
        if status == ActionExecutionStatus.FAILED:
            return RunnerExecutionStatus.FAILED
        if status == ActionExecutionStatus.TIMEOUT:
            return RunnerExecutionStatus.TIMEOUT
        return RunnerExecutionStatus.ERROR
