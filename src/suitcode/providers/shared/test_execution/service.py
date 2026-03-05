from __future__ import annotations

from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.tests.models import (
    TestExecutionResult,
    TestExecutionStatus,
    TestTargetDescription,
)
from suitcode.providers.shared.action_execution import ActionExecutionService, ActionExecutionStatus
from suitcode.providers.shared.test_execution.snippets import FailureSnippetExtractor


class TestExecutionService:
    def __init__(
        self,
        repository_root,
        suit_dir,
        action_execution_service: ActionExecutionService | None = None,
        snippet_extractor: FailureSnippetExtractor | None = None,
    ) -> None:
        self._action_execution_service = action_execution_service or ActionExecutionService(
            repository_root=repository_root,
            suit_dir=suit_dir,
        )
        self._snippet_extractor = snippet_extractor or FailureSnippetExtractor()

    def run_target(self, description: TestTargetDescription, timeout_seconds: int) -> TestExecutionResult:
        execution = self._action_execution_service.run(
            action_id=description.test_definition.id,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            timeout_seconds=timeout_seconds,
            run_group="tests",
        )
        source_tool = self._source_tool(description)
        failure_snippets = (
            tuple()
            if execution.status == ActionExecutionStatus.PASSED
            else self._snippet_extractor.extract(
                execution.output,
                self._action_execution_service.repository_root,
                source_tool=source_tool,
            )
        )
        status = self._to_test_status(execution.status)
        summary_kind = SourceKind.TEST_TOOL if description.is_authoritative else SourceKind.HEURISTIC
        provenance = (
            *description.provenance,
            derived_summary_provenance(
                source_kind=summary_kind,
                source_tool=source_tool,
                evidence_summary="test target execution result derived from deterministic provider command",
                evidence_paths=(execution.log_path, *description.test_definition.test_files),
            ),
        )
        return TestExecutionResult(
            test_id=description.test_definition.id,
            status=status,
            success=status == TestExecutionStatus.PASSED,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            log_path=execution.log_path,
            warning=description.warning,
            output_excerpt=execution.output_excerpt,
            failure_snippets=failure_snippets,
            provenance=provenance,
        )

    @staticmethod
    def _to_test_status(status: ActionExecutionStatus) -> TestExecutionStatus:
        if status == ActionExecutionStatus.PASSED:
            return TestExecutionStatus.PASSED
        if status == ActionExecutionStatus.FAILED:
            return TestExecutionStatus.FAILED
        if status == ActionExecutionStatus.TIMEOUT:
            return TestExecutionStatus.TIMEOUT
        return TestExecutionStatus.ERROR

    @staticmethod
    def _source_tool(description: TestTargetDescription) -> str | None:
        for entry in description.provenance:
            if entry.source_kind == SourceKind.TEST_TOOL and entry.source_tool is not None:
                return entry.source_tool
        return None
