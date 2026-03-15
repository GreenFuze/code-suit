from __future__ import annotations

from pathlib import Path

from suitcode.evaluation.comparison_models import EvaluationArm
from suitcode.evaluation.codex.task_models import CodexEvaluationTask


class CodexPromptLibrary:
    def build_prompt(
        self,
        task: CodexEvaluationTask,
        *,
        repository_root: Path,
        arm: EvaluationArm = EvaluationArm.SUITCODE,
        auto_orientation_hint: bool = False,
    ) -> str:
        selector_block = "\n".join(self._selector_lines(task))
        variants = (
            f"\nAcceptable variants:\n{chr(10).join(f'- {item}' for item in task.acceptable_variants)}"
            if task.acceptable_variants
            else ""
        )
        arm_note = (
            "SuitCode may be available in this environment."
            if arm == EvaluationArm.SUITCODE
            else "Some external tools may be unavailable in this environment; use only what is actually available."
        )
        orientation_hint = (
            "If a deterministic repository-intelligence or validation-surface tool is available early, prefer using it before broad exploratory searching.\n"
            if auto_orientation_hint
            else ""
        )
        return (
            f"You are running a benchmark task against the repository at {repository_root}.\n"
            f"Task id: {task.task_id}\n"
            f"Task family: {task.task_family.value}\n"
            f"Task taxonomy: {task.task_taxonomy}\n"
            f"Difficulty: {task.difficulty}\n"
            f"Question: {task.question}\n"
            f"Repository root constraint: stay within {repository_root} only.\n"
            f"Selector details:\n{selector_block}\n"
            f"Expected success criteria:\n{chr(10).join(f'- {item}' for item in task.expected_success_criteria)}"
            f"{variants}\n"
            f"{arm_note}\n"
            f"{orientation_hint}"
            "Use the tools available in your environment to answer the task.\n"
            "Do not fabricate values. If you cannot justify a field from observed evidence, leave it to the schema constraints rather than inventing it.\n"
            "Make one tool call at a time and wait for the result before deciding on the next step.\n"
            "If you execute a test or build, report only the exact target you selected and the exact observed result.\n"
            "Return only a JSON object that matches the provided output schema. Do not wrap it in markdown, code fences, or prose."
        )

    @staticmethod
    def _selector_lines(task: CodexEvaluationTask) -> tuple[str, ...]:
        if not task.target_selector:
            return ("- no explicit selector",)
        return tuple(f"- {key}: {value}" for key, value in sorted(task.target_selector.items()))
