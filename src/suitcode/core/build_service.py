from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.action_models import ActionKind, ActionQuery, ActionTargetKind, RepositoryAction
from suitcode.core.build_models import (
    BuildExecutionResult,
    BuildExecutionStatus,
    BuildProjectResult,
    BuildTargetDescription,
)
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_source_kind, preferred_source_tool
from suitcode.core.validation import validate_timeout_seconds
from suitcode.providers.shared.action_execution import ActionExecutionService, ActionExecutionStatus

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class BuildService:
    def __init__(
        self,
        repository: Repository,
        action_execution_service: ActionExecutionService | None = None,
    ) -> None:
        self._repository = repository
        self._action_execution_service = action_execution_service or ActionExecutionService(
            repository_root=repository.root,
            suit_dir=repository.suit_dir,
        )
        self._targets_by_action_id: dict[str, BuildTargetDescription] | None = None

    def list_build_targets(self) -> tuple[BuildTargetDescription, ...]:
        return tuple(sorted(self._build_targets_by_action_id().values(), key=self._target_sort_key))

    def describe_build_target(self, action_id: str) -> BuildTargetDescription:
        normalized = action_id.strip()
        if not normalized:
            raise ValueError("action_id must not be empty")
        try:
            return self._build_targets_by_action_id()[normalized]
        except KeyError as exc:
            raise ValueError(f"unknown build action id: `{normalized}`") from exc

    def build_target(self, action_id: str, timeout_seconds: int = 300) -> BuildExecutionResult:
        validate_timeout_seconds(timeout_seconds)
        target = self.describe_build_target(action_id)
        execution = self._action_execution_service.run(
            action_id=target.action_id,
            command_argv=target.invocation.argv,
            command_cwd=target.invocation.cwd,
            timeout_seconds=timeout_seconds,
            run_group="builds",
        )
        status = self._to_build_status(execution.status)
        return BuildExecutionResult(
            action_id=target.action_id,
            target_id=target.target_id,
            target_kind=target.target_kind,
            status=status,
            success=status == BuildExecutionStatus.PASSED,
            command_argv=target.invocation.argv,
            command_cwd=target.invocation.cwd,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            log_path=execution.log_path,
            output_excerpt=execution.output_excerpt,
            provenance=(
                *target.provenance,
                derived_summary_provenance(
                    source_kind=preferred_source_kind(target.provenance),
                    source_tool=preferred_source_tool(target.provenance),
                    evidence_summary="build execution result derived from deterministic build action",
                    evidence_paths=(execution.log_path, *merge_provenance_paths(target.provenance, limit=10)),
                ),
            ),
        )

    def build_project(self, timeout_seconds: int = 300) -> BuildProjectResult:
        validate_timeout_seconds(timeout_seconds)
        targets = self.list_build_targets()
        if not targets:
            raise ValueError("no deterministic build targets are available for this repository")

        results = tuple(self.build_target(item.action_id, timeout_seconds=timeout_seconds) for item in targets)
        passed = tuple(item for item in results if item.status == BuildExecutionStatus.PASSED)
        failed = tuple(item for item in results if item.status == BuildExecutionStatus.FAILED)
        errors = tuple(item for item in results if item.status == BuildExecutionStatus.ERROR)
        timeouts = tuple(item for item in results if item.status == BuildExecutionStatus.TIMEOUT)
        result_provenance = tuple(entry for item in results for entry in item.provenance)
        return BuildProjectResult(
            timeout_seconds=timeout_seconds,
            total=len(results),
            passed=len(passed),
            failed=len(failed),
            errors=len(errors),
            timeouts=len(timeouts),
            succeeded_target_ids=tuple(item.target_id for item in passed),
            failed_results=tuple(item for item in results if item.status != BuildExecutionStatus.PASSED),
            provenance=(
                derived_summary_provenance(
                    source_kind=preferred_source_kind(result_provenance),
                    source_tool=preferred_source_tool(result_provenance),
                    evidence_summary="project build summary derived from deterministic build action executions",
                    evidence_paths=merge_provenance_paths(result_provenance, limit=10),
                ),
            ),
        )

    def _build_targets_by_action_id(self) -> dict[str, BuildTargetDescription]:
        if self._targets_by_action_id is None:
            actions = self._repository.list_actions(ActionQuery(action_kinds=(ActionKind.BUILD_EXECUTION,)))
            by_id: dict[str, BuildTargetDescription] = {}
            for action in actions:
                if action.id in by_id:
                    raise ValueError(f"duplicate build action id detected: `{action.id}`")
                by_id[action.id] = self._to_build_target(action)
            self._targets_by_action_id = by_id
        return self._targets_by_action_id

    @staticmethod
    def _to_build_target(action: RepositoryAction) -> BuildTargetDescription:
        if action.kind != ActionKind.BUILD_EXECUTION:
            raise ValueError(f"action is not a build action: `{action.id}`")
        return BuildTargetDescription(
            action_id=action.id,
            name=action.name,
            provider_id=action.provider_id,
            target_id=action.target_id,
            target_kind=action.target_kind,
            owner_ids=action.owner_ids,
            invocation=action.invocation,
            dry_run_supported=action.dry_run_supported,
            provenance=action.provenance,
        )

    @staticmethod
    def _target_sort_key(target: BuildTargetDescription) -> tuple[int, str, str]:
        kind_order = {
            ActionTargetKind.COMPONENT: 0,
            ActionTargetKind.REPOSITORY: 1,
        }
        return (kind_order[target.target_kind], target.target_id, target.action_id)

    @staticmethod
    def _to_build_status(status: ActionExecutionStatus) -> BuildExecutionStatus:
        if status == ActionExecutionStatus.PASSED:
            return BuildExecutionStatus.PASSED
        if status == ActionExecutionStatus.FAILED:
            return BuildExecutionStatus.FAILED
        if status == ActionExecutionStatus.TIMEOUT:
            return BuildExecutionStatus.TIMEOUT
        return BuildExecutionStatus.ERROR
