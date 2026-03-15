from __future__ import annotations

from dataclasses import dataclass

from suitcode.evaluation.codex.task_models import (
    CodexEvaluationTask,
    CodexTaskFamily,
    default_high_value_tools,
    default_required_tools,
)


@dataclass(frozen=True)
class CodexTaskContract:
    task_family: CodexTaskFamily
    required_tools: tuple[str, ...]
    preferred_high_value_tools: tuple[str, ...]

    def prompt_steps(self, task: CodexEvaluationTask) -> tuple[str, ...]:
        selector = task.target_selector
        if self.task_family == CodexTaskFamily.ORIENTATION:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call repository_summary with the returned workspace_id and repository_id.",
                "3. Call get_truth_coverage with the same workspace_id and repository_id.",
            )
        if self.task_family == CodexTaskFamily.CHANGE_ANALYSIS:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call analyze_change with the returned workspace_id and repository_id and the provided selector.",
            )
        if self.task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call get_minimum_verified_change_set with the returned workspace_id and repository_id and the provided selector.",
            )
        if self.task_family == CodexTaskFamily.TRUTH_COVERAGE:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call get_truth_coverage with the returned workspace_id and repository_id.",
            )
        if self.task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call get_file_owner with the returned workspace_id and repository_id and the provided repository-relative path.",
                "3. Call get_related_tests with the returned workspace_id and repository_id and the same repository-relative path.",
            )
        if self.task_family == CodexTaskFamily.CI_DEBUGGING:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call get_minimum_verified_change_set with the returned workspace_id and repository_id and the provided selector.",
                "3. Determine the first deterministic test or build target from that result.",
                "4. Call the matching describe_* tool for only that selected target.",
            )
        if self.task_family == CodexTaskFamily.UNSUPPORTED_ACTION_REASONING:
            return (
                "1. Call open_workspace for this repository.",
                "2. Call get_minimum_verified_change_set with the returned workspace_id and repository_id and the provided selector.",
                "3. Call get_truth_coverage with the same workspace_id and repository_id.",
            )
        if self.task_family == CodexTaskFamily.TEST_EXECUTION:
            explicit_test_id = selector.get("test_id")
            if explicit_test_id is not None:
                return (
                    "1. Call open_workspace for this repository.",
                    "2. Call describe_test_target for the provided test_id.",
                    "3. Call run_test_targets for only that provided test_id.",
                )
            return (
                "1. Call open_workspace for this repository.",
                "2. Determine the test target to run from the available evidence in this environment.",
                "3. Call describe_test_target for the selected test.",
                "4. Call run_test_targets for only that selected test.",
            )
        if self.task_family == CodexTaskFamily.BUILD_EXECUTION:
            explicit_action_id = selector.get("action_id")
            if explicit_action_id is not None:
                return (
                    "1. Call open_workspace for this repository.",
                    "2. Call describe_build_target for the provided action_id.",
                    "3. Call build_target for only that provided action_id.",
                )
            return (
                "1. Call open_workspace for this repository.",
                "2. Determine the build target to run from the available evidence in this environment.",
                "3. Call describe_build_target for the selected action.",
                "4. Call build_target for only that selected action.",
            )
        raise ValueError(f"unsupported Codex task family `{self.task_family.value}`")

    def expected_argument_subsets(
        self,
        task: CodexEvaluationTask,
        *,
        workspace_id: str,
        repository_id: str,
    ) -> tuple[tuple[str, dict[str, object]], ...]:
        selector = dict(task.target_selector)
        if self.task_family == CodexTaskFamily.ORIENTATION:
            return (
                ("repository_summary", {"workspace_id": workspace_id, "repository_id": repository_id}),
                ("get_truth_coverage", {"workspace_id": workspace_id, "repository_id": repository_id}),
            )
        if self.task_family == CodexTaskFamily.CHANGE_ANALYSIS:
            return (("analyze_change", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),)
        if self.task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return (("get_minimum_verified_change_set", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),)
        if self.task_family == CodexTaskFamily.TRUTH_COVERAGE:
            return (("get_truth_coverage", {"workspace_id": workspace_id, "repository_id": repository_id}),)
        if self.task_family == CodexTaskFamily.BUG_FIX_NAVIGATION:
            repository_rel_path = selector.get("repository_rel_path")
            return (("get_file_owner", {"workspace_id": workspace_id, "repository_id": repository_id, "repository_rel_path": repository_rel_path}),)
        if self.task_family == CodexTaskFamily.CI_DEBUGGING:
            selector = {key: value for key, value in selector.items() if key != "requested_action_kind"}
            return (("get_minimum_verified_change_set", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),)
        if self.task_family == CodexTaskFamily.UNSUPPORTED_ACTION_REASONING:
            selector = {key: value for key, value in selector.items() if key != "requested_action_kind"}
            return (
                ("get_minimum_verified_change_set", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),
                ("get_truth_coverage", {"workspace_id": workspace_id, "repository_id": repository_id}),
            )
        return ()


_CONTRACTS: dict[CodexTaskFamily, CodexTaskContract] = {
    family: CodexTaskContract(
        task_family=family,
        required_tools=default_required_tools(family),
        preferred_high_value_tools=default_high_value_tools(family),
    )
    for family in CodexTaskFamily
}


def contract_for(task_family: CodexTaskFamily) -> CodexTaskContract:
    return _CONTRACTS[task_family]
