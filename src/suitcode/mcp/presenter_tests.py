from __future__ import annotations

from suitcode.core.repository import Repository
from suitcode.core.tests.models import DiscoveredTestDefinition, ResolvedRelatedTest
from suitcode.mcp.models import (
    RelatedTestView,
    RunTestTargetsView,
    TestDefinitionView,
    TestExecutionResultView,
    TestFailureSnippetView,
    TestsSnapshotView,
    TestTargetDescriptionView,
)
from suitcode.mcp.presenter_common import compact_provenance_views, provenance_views


class TestPresenter:
    def test_view(self, discovered_test: DiscoveredTestDefinition) -> TestDefinitionView:
        test_definition = discovered_test.test_definition
        return TestDefinitionView(
            id=test_definition.id,
            name=test_definition.name,
            framework=test_definition.framework.value,
            test_files=test_definition.test_files,
            provenance=provenance_views(discovered_test.provenance),
        )

    def tests_snapshot(self, repository: Repository) -> TestsSnapshotView:
        return TestsSnapshotView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            provider_ids=tuple(provider.__class__.descriptor().provider_id for provider in repository.tests.providers),
            test_count=len(repository.tests.get_discovered_tests()),
        )

    def related_test_view(self, related_test: ResolvedRelatedTest) -> RelatedTestView:
        match = related_test.match
        discovered_test = related_test.discovered_test
        return RelatedTestView(
            id=discovered_test.test_definition.id,
            name=discovered_test.test_definition.name,
            framework=discovered_test.test_definition.framework.value,
            test_file_count=len(discovered_test.test_definition.test_files),
            test_files_preview=discovered_test.test_definition.test_files[:5],
            relation_reason=match.relation_reason,
            matched_owner_id=match.matched_owner_id,
            matched_path=match.matched_repository_rel_path,
            provenance=compact_provenance_views(related_test.provenance),
        )

    def test_target_description_view(self, description) -> TestTargetDescriptionView:
        test_definition = description.test_definition
        return TestTargetDescriptionView(
            id=test_definition.id,
            name=test_definition.name,
            framework=test_definition.framework.value,
            test_files=test_definition.test_files,
            command_argv=description.command_argv,
            command_cwd=description.command_cwd,
            is_authoritative=description.is_authoritative,
            warning=description.warning,
            provenance=provenance_views(description.provenance),
        )

    def test_execution_result_view(self, result) -> TestExecutionResultView:
        return TestExecutionResultView(
            test_id=result.test_id,
            status=result.status.value,
            success=result.success,
            command_argv=result.command_argv,
            command_cwd=result.command_cwd,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            log_path=result.log_path,
            warning=result.warning,
            output_excerpt=result.output_excerpt,
            failure_snippets=tuple(
                TestFailureSnippetView(
                    repository_rel_path=item.repository_rel_path,
                    line_start=item.line_start,
                    line_end=item.line_end,
                    snippet=item.snippet,
                    provenance=provenance_views(item.provenance),
                )
                for item in result.failure_snippets
            ),
            provenance=provenance_views(result.provenance),
        )

    def run_test_targets_view(
        self,
        workspace_id: str,
        repository_id: str,
        timeout_seconds: int,
        results,
    ) -> RunTestTargetsView:
        views = tuple(self.test_execution_result_view(item) for item in results)
        passed = sum(1 for item in views if item.status == "passed")
        failed = sum(1 for item in views if item.status == "failed")
        errors = sum(1 for item in views if item.status == "error")
        timeouts = sum(1 for item in views if item.status == "timeout")
        return RunTestTargetsView(
            workspace_id=workspace_id,
            repository_id=repository_id,
            timeout_seconds=timeout_seconds,
            total=len(views),
            passed=passed,
            failed=failed,
            errors=errors,
            timeouts=timeouts,
            results=views,
        )
