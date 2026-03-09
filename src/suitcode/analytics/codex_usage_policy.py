from __future__ import annotations

from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.native_agent_models import CodexSessionAnalytics
from suitcode.analytics.transcript_models import TranscriptCapture, TranscriptSegmentKind


LATE_SUITCODE_TOOL_INDEX_THRESHOLD = 6
LATE_HIGH_VALUE_TOOL_INDEX_THRESHOLD = 4
SHELL_HEAVY_PRE_SUITCODE_NON_SUITCODE_CALL_THRESHOLD = 3


def is_late_suitcode_adoption(first_tool_index: int | None) -> bool:
    return first_tool_index is not None and first_tool_index > LATE_SUITCODE_TOOL_INDEX_THRESHOLD


def is_late_high_value_adoption(first_high_value_tool_index: int | None) -> bool:
    return (
        first_high_value_tool_index is not None
        and first_high_value_tool_index > LATE_HIGH_VALUE_TOOL_INDEX_THRESHOLD
    )


def is_high_value_tool(tool_name: str | None) -> bool:
    return tool_name in HIGH_VALUE_TOOL_SET


def shell_heavy_before_first_suitcode(capture: TranscriptCapture | None) -> bool:
    if capture is None:
        return False
    first_suitcode_sequence_index = next(
        (
            segment.sequence_index
            for segment in capture.segments
            if segment.kind == TranscriptSegmentKind.MCP_TOOL_CALL and segment.is_suitcode
        ),
        None,
    )
    if first_suitcode_sequence_index is None:
        return False

    non_suitcode_tool_calls = 0
    saw_shell_or_custom = False
    for segment in capture.segments:
        if segment.sequence_index >= first_suitcode_sequence_index:
            break
        if segment.kind == TranscriptSegmentKind.MCP_TOOL_CALL and not segment.is_suitcode:
            non_suitcode_tool_calls += 1
        elif segment.kind == TranscriptSegmentKind.CUSTOM_TOOL_CALL:
            non_suitcode_tool_calls += 1
            saw_shell_or_custom = True
        elif segment.kind in {
            TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT,
            TranscriptSegmentKind.TERMINAL_OUTPUT,
        }:
            saw_shell_or_custom = True

    return (
        non_suitcode_tool_calls >= SHELL_HEAVY_PRE_SUITCODE_NON_SUITCODE_CALL_THRESHOLD
        and saw_shell_or_custom
    )


def with_usage_flags(session: CodexSessionAnalytics) -> CodexSessionAnalytics:
    return session.model_copy(
        update={
            "late_suitcode_adoption": is_late_suitcode_adoption(session.first_suitcode_tool_index),
            "late_high_value_suitcode_adoption": is_late_high_value_adoption(
                session.first_high_value_suitcode_tool_index
            ),
            "used_no_high_value_suitcode_tool": session.used_suitcode
            and session.first_high_value_suitcode_tool is None,
            "shell_heavy_before_suitcode": shell_heavy_before_first_suitcode(
                session.transcript_capture
            ),
        }
    )
