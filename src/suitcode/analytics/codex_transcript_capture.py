from __future__ import annotations

import json
from pathlib import Path

from suitcode.analytics.codex_rollout_utils import (
    canonical_suitcode_tool_name,
    is_mcp_tool_name,
    iter_rollout_events,
    message_text,
    optional_non_empty,
    optional_resolved_path,
    parse_datetime,
    required_non_empty,
)
from suitcode.analytics.transcript_models import (
    TranscriptCapture,
    TranscriptSegment,
    TranscriptSegmentKind,
)


class CodexTranscriptCaptureBuilder:
    def build(self, path: Path) -> TranscriptCapture:
        artifact_path = path.expanduser().resolve()
        if not artifact_path.is_file():
            raise ValueError(f"Codex session artifact does not exist: `{artifact_path}`")

        session_id: str | None = None
        repository_root: str | None = None
        sequence_index = 0
        segments: list[TranscriptSegment] = []
        call_index: dict[str, _CallInfo] = {}

        for line_number, event in iter_rollout_events(artifact_path):
            event_type = event.get("type")
            if event_type == "session_meta":
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError(f"invalid session_meta payload in `{artifact_path}` at line {line_number}")
                current_session_id = required_non_empty(payload.get("id"), "session id", artifact_path)
                if session_id is None:
                    session_id = current_session_id
                elif session_id != current_session_id:
                    raise ValueError(f"inconsistent session id in `{artifact_path}`")
                cwd = optional_resolved_path(payload.get("cwd"), artifact_path)
                repository_root = str(cwd) if cwd is not None else None
                continue

            if event_type != "response_item":
                continue
            if session_id is None:
                raise ValueError(f"response_item found before session_meta in `{artifact_path}`")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                raise ValueError(f"invalid response_item payload in `{artifact_path}` at line {line_number}")
            timestamp = self._timestamp_text(event, artifact_path=artifact_path, line_number=line_number)
            payload_type = payload.get("type")

            if payload_type == "message":
                message_segments = self._message_segments(
                    session_id=session_id,
                    payload=payload,
                    timestamp=timestamp,
                    artifact_path=artifact_path,
                    line_number=line_number,
                    starting_sequence=sequence_index,
                )
                segments.extend(message_segments)
                sequence_index += len(message_segments)
                continue

            if payload_type in {"function_call", "custom_tool_call"}:
                segment, call_info = self._tool_call_segment(
                    session_id=session_id,
                    payload=payload,
                    timestamp=timestamp,
                    artifact_path=artifact_path,
                    line_number=line_number,
                    sequence_index=sequence_index + 1,
                )
                segments.append(segment)
                sequence_index += 1
                if call_info.call_id in call_index:
                    raise ValueError(f"duplicate call_id `{call_info.call_id}` in `{artifact_path}`")
                call_index[call_info.call_id] = call_info
                continue

            if payload_type in {"function_call_output", "custom_tool_call_output"}:
                segment = self._tool_output_segment(
                    session_id=session_id,
                    payload=payload,
                    timestamp=timestamp,
                    artifact_path=artifact_path,
                    line_number=line_number,
                    sequence_index=sequence_index + 1,
                    call_index=call_index,
                )
                segments.append(segment)
                sequence_index += 1
                continue

            if payload_type in {"reasoning", "response_reasoning"}:
                reasoning_segments = self._reasoning_segments(
                    session_id=session_id,
                    payload=payload,
                    timestamp=timestamp,
                    sequence_index=sequence_index,
                )
                segments.extend(reasoning_segments)
                sequence_index += len(reasoning_segments)
                continue

        if session_id is None:
            raise ValueError(f"missing session_meta in `{artifact_path}`")
        return TranscriptCapture(
            session_id=session_id,
            repository_root=repository_root,
            artifact_path=str(artifact_path),
            segments=tuple(segments),
        )

    @staticmethod
    def _timestamp_text(event: dict[str, object], *, artifact_path: Path, line_number: int) -> str:
        raw_value = event.get("timestamp")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"missing event timestamp in `{artifact_path}` at line {line_number}")
        return parse_datetime(raw_value, artifact_path=artifact_path).isoformat().replace("+00:00", "Z")

    def _message_segments(
        self,
        *,
        session_id: str,
        payload: dict[str, object],
        timestamp: str,
        artifact_path: Path,
        line_number: int,
        starting_sequence: int,
    ) -> tuple[TranscriptSegment, ...]:
        role = optional_non_empty(payload.get("role"))
        if role not in {"user", "assistant"}:
            return ()
        content_text = message_text(payload.get("content"))
        if not content_text:
            return ()
        kind = (
            TranscriptSegmentKind.USER_MESSAGE
            if role == "user"
            else TranscriptSegmentKind.ASSISTANT_MESSAGE
        )
        return (
            TranscriptSegment(
                segment_id=f"{session_id}:segment:{starting_sequence + 1}",
                session_id=session_id,
                sequence_index=starting_sequence + 1,
                timestamp_utc=timestamp,
                kind=kind,
                role=role,
                content_text=content_text,
                content_bytes=len(content_text.encode("utf-8")),
            ),
        )

    def _tool_call_segment(
        self,
        *,
        session_id: str,
        payload: dict[str, object],
        timestamp: str,
        artifact_path: Path,
        line_number: int,
        sequence_index: int,
    ) -> tuple[TranscriptSegment, "_CallInfo"]:
        tool_name = required_non_empty(payload.get("name"), "tool call name", artifact_path)
        call_id = required_non_empty(payload.get("call_id"), "tool call id", artifact_path)
        arguments_text = self._json_like_text(payload.get("arguments"))
        is_mcp = is_mcp_tool_name(tool_name)
        canonical_name = canonical_suitcode_tool_name(tool_name)
        kind = TranscriptSegmentKind.MCP_TOOL_CALL if is_mcp else TranscriptSegmentKind.CUSTOM_TOOL_CALL
        content_text = f"tool:{tool_name}\narguments:{arguments_text}"
        segment = TranscriptSegment(
            segment_id=f"{session_id}:segment:{sequence_index}",
            session_id=session_id,
            sequence_index=sequence_index,
            timestamp_utc=timestamp,
            kind=kind,
            tool_name=tool_name,
            content_text=content_text,
            content_bytes=len(content_text.encode("utf-8")),
            metadata={"call_id": call_id, "arguments_text": arguments_text},
            is_mcp=is_mcp,
            is_suitcode=canonical_name is not None,
            canonical_tool_name=canonical_name,
        )
        return segment, _CallInfo(
            call_id=call_id,
            tool_name=tool_name,
            kind=kind,
            is_mcp=is_mcp,
            is_suitcode=(canonical_name is not None),
            canonical_tool_name=canonical_name,
        )

    def _tool_output_segment(
        self,
        *,
        session_id: str,
        payload: dict[str, object],
        timestamp: str,
        artifact_path: Path,
        line_number: int,
        sequence_index: int,
        call_index: dict[str, "_CallInfo"],
    ) -> TranscriptSegment:
        call_id = required_non_empty(payload.get("call_id"), "tool output call_id", artifact_path)
        call_info = call_index.get(call_id)
        if call_info is None:
            raise ValueError(f"unknown tool output call_id `{call_id}` in `{artifact_path}` at line {line_number}")
        output_text = self._json_like_text(payload.get("output"))
        kind = (
            TranscriptSegmentKind.MCP_TOOL_OUTPUT
            if call_info.kind == TranscriptSegmentKind.MCP_TOOL_CALL
            else TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT
        )
        content_text = f"tool:{call_info.tool_name}\noutput:{output_text}"
        return TranscriptSegment(
            segment_id=f"{session_id}:segment:{sequence_index}",
            session_id=session_id,
            sequence_index=sequence_index,
            timestamp_utc=timestamp,
            kind=kind,
            tool_name=call_info.tool_name,
            content_text=content_text,
            content_bytes=len(content_text.encode("utf-8")),
            metadata={"call_id": call_id, "output_text": output_text},
            is_mcp=call_info.is_mcp,
            is_suitcode=call_info.is_suitcode,
            canonical_tool_name=call_info.canonical_tool_name,
        )

    def _reasoning_segments(
        self,
        *,
        session_id: str,
        payload: dict[str, object],
        timestamp: str,
        sequence_index: int,
    ) -> tuple[TranscriptSegment, ...]:
        summaries = payload.get("summary")
        if not isinstance(summaries, list):
            return ()
        segments: list[TranscriptSegment] = []
        next_index = sequence_index + 1
        for item in summaries:
            if not isinstance(item, dict):
                continue
            text = optional_non_empty(item.get("text"))
            if text is None:
                continue
            segments.append(
                TranscriptSegment(
                    segment_id=f"{session_id}:segment:{next_index}",
                    session_id=session_id,
                    sequence_index=next_index,
                    timestamp_utc=timestamp,
                    kind=TranscriptSegmentKind.REASONING_SUMMARY,
                    content_text=text,
                    content_bytes=len(text.encode("utf-8")),
                )
            )
            next_index += 1
        return tuple(segments)

    @staticmethod
    def _json_like_text(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=True, sort_keys=True)


class _CallInfo:
    def __init__(
        self,
        *,
        call_id: str,
        tool_name: str,
        kind: TranscriptSegmentKind,
        is_mcp: bool,
        is_suitcode: bool,
        canonical_tool_name: str | None,
    ) -> None:
        self.call_id = call_id
        self.tool_name = tool_name
        self.kind = kind
        self.is_mcp = is_mcp
        self.is_suitcode = is_suitcode
        self.canonical_tool_name = canonical_tool_name
