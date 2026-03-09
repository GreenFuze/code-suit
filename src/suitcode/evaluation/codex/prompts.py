from __future__ import annotations

from pathlib import Path

from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.task_contracts import contract_for
from suitcode.evaluation.codex.task_models import CodexEvaluationTask, CodexTaskFamily


class CodexPromptLibrary:
    def build_prompt(
        self,
        task: CodexEvaluationTask,
        *,
        repository_root: Path,
        arm: EvaluationArm = EvaluationArm.SUITCODE,
    ) -> str:
        if arm == EvaluationArm.BASELINE:
            return self._build_baseline_prompt(task, repository_root=repository_root)
        contract = contract_for(task.task_family)
        selector_lines = self._selector_lines(task)
        required_flow = contract.prompt_steps(task)
        family_objective = {
            CodexTaskFamily.ORIENTATION: "Summarize the repository and assess trust coverage.",
            CodexTaskFamily.CHANGE_ANALYSIS: "Analyze the requested change target deterministically with analyze_change.",
            CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "Compute the exact minimum verified change set for the requested target.",
            CodexTaskFamily.TRUTH_COVERAGE: "Assess repository truth coverage across all supported domains.",
            CodexTaskFamily.TEST_EXECUTION: "Find the correct deterministic test target, describe it, and execute only that target.",
            CodexTaskFamily.BUILD_EXECUTION: "Find the correct deterministic build target, describe it, and execute only that target.",
        }[task.task_family]
        exact_mapping = {
            CodexTaskFamily.ORIENTATION: (
                "Copy workspace_id and repository_id exactly from open_workspace. "
                "Copy provider_ids, component_count, test_count, and quality_provider_count exactly from repository_summary with preview_limit=8. "
                "Copy overall_truth_availability exactly from get_truth_coverage. "
                "Do not infer repository_summary fields from get_truth_coverage."
            ),
            CodexTaskFamily.CHANGE_ANALYSIS: "Copy the values from analyze_change exactly into target_kind, owner_id, primary_component_id, related_test_ids, quality_gate_provider_ids, evidence_edge_count, and overall_truth_availability.",
            CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "Copy the values from get_minimum_verified_change_set exactly into owner_id, primary_component_id, test_target_ids, build_target_ids, runner_action_ids, quality_validation_operation_ids, and quality_hygiene_operation_ids.",
            CodexTaskFamily.TRUTH_COVERAGE: (
                "Copy the values from get_truth_coverage exactly. "
                "Do not summarize, infer, or use placeholder unavailable/0 values. "
                "overall_availability must equal the tool output exactly. "
                "For each domain object in get_truth_coverage.domains, match by domain name and copy availability, "
                "authoritative_count, derived_count, heuristic_count, and unavailable_count exactly into the corresponding "
                "architecture, code, tests, quality, and actions fields."
            ),
            CodexTaskFamily.TEST_EXECUTION: "Copy the selected deterministic test target and execution result exactly into selected_test_id, command_preview, execution_status, passed, failed, errors, and timeouts.",
            CodexTaskFamily.BUILD_EXECUTION: "Copy the selected deterministic build action and execution result exactly into selected_action_id, command_preview, execution_status, and succeeded.",
        }[task.task_family]
        required_tools = ", ".join(task.expected_required_tools)
        preferred_tools = ", ".join(task.expected_high_value_tools)
        selector_block = "\n".join(selector_lines)
        flow_block = "\n".join(required_flow)
        return (
            f"You are evaluating SuitCode on the repository at {repository_root}.\n"
            f"Task id: {task.task_id}.\n"
            f"Task family: {task.task_family.value}.\n"
            f"Objective: {family_objective}\n"
            f"Required SuitCode tools: {required_tools}.\n"
            f"Preferred high-value tools: {preferred_tools}.\n"
            f"Target details:\n{selector_block}\n"
            "Required tool flow:\n"
            f"{flow_block}\n"
            f"Exact output mapping: {exact_mapping}\n"
            "Make exactly one tool call at a time. Wait for the full result of each required SuitCode tool before deciding on the next step.\n"
            "Do not call update_plan or any non-SuitCode tool during this evaluation task.\n"
            "Do not use shell commands, custom tools, or filesystem exploration before the required SuitCode tools.\n"
            "Do not use broad list/find exploration when a direct high-value SuitCode tool for this task exists.\n"
            "Do not substitute guessed defaults when a required SuitCode tool returned real values.\n"
            "If a required SuitCode tool fails, stop broad exploration immediately. Do not retry with shell or filesystem exploration.\n"
            "Return only a JSON object that matches the provided output schema. Do not wrap it in markdown, explanations, or prose."
        )

    def _build_baseline_prompt(self, task: CodexEvaluationTask, *, repository_root: Path) -> str:
        selector_lines = self._selector_lines(task)
        selector_block = "\n".join(selector_lines)
        family_objective = {
            CodexTaskFamily.ORIENTATION: "Summarize the repository and assess trust coverage without using SuitCode.",
            CodexTaskFamily.CHANGE_ANALYSIS: "Analyze the requested change target without using SuitCode.",
            CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "Infer the smallest exact validation set you can justify without SuitCode.",
            CodexTaskFamily.TRUTH_COVERAGE: "Assess repository trust coverage without using SuitCode.",
            CodexTaskFamily.TEST_EXECUTION: "Discover and execute the correct test target without using SuitCode.",
            CodexTaskFamily.BUILD_EXECUTION: "Discover and execute the correct build target without using SuitCode.",
        }[task.task_family]
        baseline_steps = {
            CodexTaskFamily.ORIENTATION: (
                "1. Explore the repository files and manifests directly.",
                "2. Identify providers/components/tests/quality tools from repository evidence.",
                "3. Infer overall trust availability conservatively from the visible toolchain evidence.",
            ),
            CodexTaskFamily.CHANGE_ANALYSIS: (
                "1. Inspect the exact target file/owner/symbol context from repository files.",
                "2. Use search/static inspection to determine owner, related tests, and quality tooling.",
                "3. Return only fields you can justify from repository evidence.",
            ),
            CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: (
                "1. Inspect the exact target context in repository files/manifests.",
                "2. Identify the narrowest tests/builds/quality operations you can justify.",
                "3. Return exact IDs only when you can derive them from visible repository evidence.",
            ),
            CodexTaskFamily.TRUTH_COVERAGE: (
                "1. Inspect manifests, config files, and repository layout directly.",
                "2. Determine whether architecture, code, tests, quality, and actions appear available, degraded, or unavailable.",
                "3. Copy only values you can support from direct repository evidence.",
            ),
            CodexTaskFamily.TEST_EXECUTION: (
                "1. Inspect the repository to identify the intended test target.",
                "2. Execute only the chosen target using direct shell/tool invocation.",
                "3. Return the exact command preview and execution result.",
            ),
            CodexTaskFamily.BUILD_EXECUTION: (
                "1. Inspect the repository to identify the intended build target.",
                "2. Execute only the chosen build target using direct shell/tool invocation.",
                "3. Return the exact command preview and execution result.",
            ),
        }[task.task_family]
        output_mapping = {
            CodexTaskFamily.ORIENTATION: "Return provider_ids, component_count, test_count, quality_provider_count, and overall_truth_availability only from direct repository evidence.",
            CodexTaskFamily.CHANGE_ANALYSIS: "Return target_kind, owner_id, primary_component_id, related_test_ids, quality_gate_provider_ids, evidence_edge_count, and overall_truth_availability only from evidence you can justify directly.",
            CodexTaskFamily.MINIMUM_VERIFIED_CHANGE_SET: "Return owner_id, primary_component_id, test_target_ids, build_target_ids, runner_action_ids, quality_validation_operation_ids, and quality_hygiene_operation_ids only when you can justify them directly.",
            CodexTaskFamily.TRUTH_COVERAGE: "Return the per-domain availability and counts conservatively from direct repository evidence. Do not fabricate authoritative counts.",
            CodexTaskFamily.TEST_EXECUTION: "Return selected_test_id, command_preview, execution_status, passed, failed, errors, and timeouts from the exact command you executed.",
            CodexTaskFamily.BUILD_EXECUTION: "Return selected_action_id, command_preview, execution_status, and succeeded from the exact command you executed.",
        }[task.task_family]
        return (
            f"You are evaluating a baseline Codex run on the repository at {repository_root}.\n"
            f"Task id: {task.task_id}.\n"
            f"Task family: {task.task_family.value}.\n"
            f"Objective: {family_objective}\n"
            f"Target details:\n{selector_block}\n"
            "Baseline flow:\n"
            f"{chr(10).join(baseline_steps)}\n"
            f"Exact output mapping: {output_mapping}\n"
            "Do not use SuitCode or assume SuitCode outputs exist.\n"
            "Use direct filesystem, manifest, search, and shell evidence as needed.\n"
            "Do not fabricate values. If a field cannot be justified, infer conservatively from direct evidence only.\n"
            "Return only a JSON object that matches the provided output schema. Do not wrap it in markdown, explanations, or prose."
        )

    @staticmethod
    def _selector_lines(task: CodexEvaluationTask) -> tuple[str, ...]:
        if not task.target_selector:
            return ("- no explicit selector",)
        return tuple(f"- {key}: {value}" for key, value in sorted(task.target_selector.items()))
