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
                "2. Call repository_summary with the returned workspace_id and repository_id and preview_limit set to 8.",
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
                "2. Call list_tests.",
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
                "2. Call list_build_targets.",
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
                ("repository_summary", {"workspace_id": workspace_id, "repository_id": repository_id, "preview_limit": 8}),
                ("get_truth_coverage", {"workspace_id": workspace_id, "repository_id": repository_id}),
            )
        if self.task_family == CodexTaskFamily.CHANGE_ANALYSIS:
            return (("analyze_change", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),)
        if self.task_family == CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET:
            return (("get_minimum_verified_change_set", {"workspace_id": workspace_id, "repository_id": repository_id, **selector}),)
        if self.task_family == CodexTaskFamily.TRUTH_COVERAGE:
            return (("get_truth_coverage", {"workspace_id": workspace_id, "repository_id": repository_id}),)
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
