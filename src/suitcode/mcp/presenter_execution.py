from __future__ import annotations

from suitcode.core.action_models import RepositoryAction
from suitcode.core.build_models import BuildExecutionResult, BuildProjectResult, BuildTargetDescription
from suitcode.core.runner_models import RunnerContext, RunnerExecutionResult
from suitcode.core.repository import Repository
from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult
from suitcode.mcp.models import (
    ActionInvocationView,
    ActionView,
    BuildExecutionResultView,
    BuildProjectResultView,
    BuildTargetDescriptionView,
    QualityDiagnosticView,
    QualityEntityDeltaView,
    QualityFileResultView,
    QualitySnapshotView,
    RunnerContextView,
    RunnerExecutionResultView,
)
from suitcode.mcp.presenter_architecture import ArchitecturePresenter
from suitcode.mcp.presenter_code import CodePresenter
from suitcode.mcp.presenter_common import provenance_views
from suitcode.mcp.presenter_tests import TestPresenter


class RunnerPresenter:
    def __init__(self) -> None:
        self._architecture_presenter = ArchitecturePresenter()
        self._test_presenter = TestPresenter()

    def runner_context_view(self, context: RunnerContext) -> RunnerContextView:
        return RunnerContextView(
            runner=self._architecture_presenter.runner_view(context.runner),
            action_id=context.action_id,
            provider_id=context.provider_id,
            invocation=ActionInvocationView(argv=context.invocation.argv, cwd=context.invocation.cwd),
            primary_component=(
                self._architecture_presenter.component_view(context.primary_component)
                if context.primary_component is not None
                else None
            ),
            owned_file_count=context.owned_file_count,
            owned_files_preview=tuple(self._architecture_presenter.file_view(item) for item in context.owned_files_preview),
            related_test_count=context.related_test_count,
            related_tests_preview=tuple(self._test_presenter.related_test_view(item) for item in context.related_tests_preview),
            provenance=provenance_views(context.provenance),
        )

    def runner_execution_result_view(self, result: RunnerExecutionResult) -> RunnerExecutionResultView:
        return RunnerExecutionResultView(
            runner_id=result.runner_id,
            action_id=result.action_id,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            output_excerpt=result.output_excerpt,
            provenance=provenance_views(result.provenance),
        )


class BuildPresenter:
    def build_target_description_view(self, target: BuildTargetDescription) -> BuildTargetDescriptionView:
        return BuildTargetDescriptionView(
            action_id=target.action_id,
            name=target.name,
            provider_id=target.provider_id,
            target_id=target.target_id,
            target_kind=target.target_kind.value,
            owner_ids=target.owner_ids,
            invocation=ActionInvocationView(argv=target.invocation.argv, cwd=target.invocation.cwd),
            dry_run_supported=target.dry_run_supported,
            provenance=provenance_views(target.provenance),
        )

    def build_execution_result_view(self, result: BuildExecutionResult) -> BuildExecutionResultView:
        return BuildExecutionResultView(
            action_id=result.action_id,
            target_id=result.target_id,
            target_kind=result.target_kind.value,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            output_excerpt=result.output_excerpt,
            provenance=provenance_views(result.provenance),
        )

    def build_project_result_view(self, result: BuildProjectResult) -> BuildProjectResultView:
        return BuildProjectResultView(
            timeout_seconds=result.timeout_seconds,
            total=result.total,
            passed=result.passed,
            failed=result.failed,
            errors=result.errors,
            timeouts=result.timeouts,
            succeeded_target_ids=result.succeeded_target_ids,
            failed_results=tuple(self.build_execution_result_view(item) for item in result.failed_results),
            provenance=provenance_views(result.provenance),
        )


class QualityPresenter:
    def __init__(self) -> None:
        self._code_presenter = CodePresenter()

    def diagnostic_view(self, diagnostic: QualityDiagnostic) -> QualityDiagnosticView:
        return QualityDiagnosticView(
            **diagnostic.model_dump(exclude={"provenance"}),
            provenance=provenance_views(diagnostic.provenance),
        )

    def entity_delta_view(self, delta: QualityEntityDelta) -> QualityEntityDeltaView:
        return QualityEntityDeltaView(
            added=tuple(self._code_presenter.symbol_view(item) for item in delta.added),
            removed=tuple(self._code_presenter.symbol_view(item) for item in delta.removed),
            updated=tuple(self._code_presenter.symbol_view(item) for item in delta.updated),
            provenance=provenance_views(delta.provenance),
        )

    def quality_file_result_view(
        self,
        workspace_id: str,
        repository_id: str,
        provider_id: str,
        result: QualityFileResult,
    ) -> QualityFileResultView:
        return QualityFileResultView(
            workspace_id=workspace_id,
            repository_id=repository_id,
            provider_id=provider_id,
            repository_rel_path=result.repository_rel_path,
            tool=result.tool,
            operation=result.operation,
            changed=result.changed,
            success=result.success,
            message=result.message,
            diagnostics=tuple(self.diagnostic_view(item) for item in result.diagnostics),
            entity_delta=self.entity_delta_view(result.entity_delta),
            applied_fixes=result.applied_fixes,
            content_sha_before=result.content_sha_before,
            content_sha_after=result.content_sha_after,
            provenance=provenance_views(result.provenance),
        )

    def quality_snapshot(self, repository: Repository) -> QualitySnapshotView:
        return QualitySnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=repository.quality.provider_ids,
        )


class ActionPresenter:
    def action_view(self, action: RepositoryAction) -> ActionView:
        return ActionView(
            id=action.id,
            name=action.name,
            kind=action.kind.value,
            provider_id=action.provider_id,
            target_id=action.target_id,
            target_kind=action.target_kind.value,
            owner_ids=action.owner_ids,
            invocation=ActionInvocationView(argv=action.invocation.argv, cwd=action.invocation.cwd),
            dry_run_supported=action.dry_run_supported,
            provenance=provenance_views(action.provenance),
        )
