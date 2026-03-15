from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from suitcode.analytics.native_agent_models import CodexSessionAnalytics
from suitcode.analytics.transcript_models import TranscriptSegmentKind
from suitcode.evaluation.models import ActionScore, AnswerScore, ArgumentScore, ToolSelectionScore


@dataclass(frozen=True)
class SuitCodeToolCall:
    tool_name: str
    arguments: dict[str, object]
    call_index: int


class CodexEvaluationScorer:
    def tool_calls(self, session: CodexSessionAnalytics) -> tuple[SuitCodeToolCall, ...]:
        capture = session.transcript_capture
        if capture is None:
            return ()
        calls: list[SuitCodeToolCall] = []
        call_index = 0
        for segment in capture.segments:
            if segment.kind != TranscriptSegmentKind.MCP_TOOL_CALL or not segment.is_suitcode:
                continue
            call_index += 1
            args_text = segment.metadata.get("arguments_text") if isinstance(segment.metadata, dict) else None
            arguments = self._parse_arguments(args_text)
            calls.append(
                SuitCodeToolCall(
                    tool_name=segment.canonical_tool_name or segment.tool_name or "",
                    arguments=arguments,
                    call_index=call_index,
                )
            )
        return tuple(calls)

    def tool_selection_score(
        self,
        session: CodexSessionAnalytics,
        *,
        required_tools: tuple[str, ...],
    ) -> ToolSelectionScore:
        used_tools = tuple(tool.tool_name for tool in session.suitcode_tools)
        missing = tuple(tool for tool in required_tools if tool not in used_tools)
        return ToolSelectionScore(
            required_tools_present=not missing,
            required_tool_names=required_tools,
            used_tool_names=used_tools,
            missing_required_tools=missing,
            first_suitcode_tool=session.first_suitcode_tool,
            first_high_value_tool=session.first_high_value_suitcode_tool,
            first_high_value_tool_index=session.first_high_value_suitcode_tool_index,
            used_high_value_tool_early=(
                session.first_high_value_suitcode_tool_index is not None
                and session.first_high_value_suitcode_tool_index <= 3
            ),
        )

    def argument_scores(
        self,
        session: CodexSessionAnalytics,
        *,
        expected_argument_subsets: tuple[tuple[str, dict[str, object]], ...],
    ) -> tuple[ArgumentScore, ...]:
        calls = self.tool_calls(session)
        results: list[ArgumentScore] = []
        for tool_name, expected in expected_argument_subsets:
            matching_calls = [call for call in calls if call.tool_name == tool_name]
            if not matching_calls:
                results.append(ArgumentScore(tool_name=tool_name, expected_argument_subset=expected, matched=False, mismatches=("tool not called",)))
                continue
            call = matching_calls[-1]
            mismatches: list[str] = []
            for key, value in expected.items():
                actual = call.arguments.get(key)
                if isinstance(value, tuple) and isinstance(actual, list):
                    matched = tuple(actual) == value
                else:
                    matched = actual == value
                if not matched:
                    mismatches.append(f"{key}: expected {value!r}, got {actual!r}")
            results.append(
                ArgumentScore(
                    tool_name=tool_name,
                    expected_argument_subset=expected,
                    matched=not mismatches,
                    mismatches=tuple(mismatches),
                )
            )
        return tuple(results)

    def answer_score(
        self,
        *,
        actual_answer: dict[str, object] | None,
        expected_answer: dict[str, object],
        schema_valid: bool,
        ignored_fields: tuple[str, ...] = (),
    ) -> AnswerScore:
        comparable_fields = tuple(key for key in expected_answer if key not in ignored_fields)
        if actual_answer is None:
            return AnswerScore(schema_valid=False, field_matches={}, missing_fields=comparable_fields, mismatched_fields=tuple())
        field_matches: dict[str, bool] = {}
        missing_fields: list[str] = []
        mismatched_fields: list[str] = []
        for key, expected in expected_answer.items():
            if key in ignored_fields:
                continue
            if key not in actual_answer:
                field_matches[key] = False
                missing_fields.append(key)
                continue
            actual = actual_answer[key]
            matched = actual == expected
            field_matches[key] = matched
            if not matched:
                mismatched_fields.append(key)
        return AnswerScore(
            schema_valid=schema_valid,
            field_matches=field_matches,
            missing_fields=tuple(missing_fields),
            mismatched_fields=tuple(mismatched_fields),
        )

    def action_score(
        self,
        session: CodexSessionAnalytics,
        *,
        required_action_kind: str | None,
        required_action_target_id: str | None,
        expected_status: str | None,
    ) -> ActionScore:
        if required_action_kind is None or required_action_target_id is None:
            return ActionScore(executed=False, matched_target=False)
        tool_name = "run_test_targets" if required_action_kind == "test" else "build_target"
        arg_key = "test_ids" if required_action_kind == "test" else "action_id"
        for call in self.tool_calls(session):
            if call.tool_name != tool_name:
                continue
            actual_target = call.arguments.get(arg_key)
            matched_target = (
                tuple(actual_target) == (required_action_target_id,)
                if isinstance(actual_target, list)
                else actual_target == required_action_target_id
            )
            return ActionScore(
                required_action_kind=required_action_kind,
                required_action_target_id=required_action_target_id,
                executed=True,
                matched_target=matched_target,
                status=expected_status,
            )
        return ActionScore(
            required_action_kind=required_action_kind,
            required_action_target_id=required_action_target_id,
            executed=False,
            matched_target=False,
            status=expected_status,
        )

    @staticmethod
    def _parse_arguments(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}
