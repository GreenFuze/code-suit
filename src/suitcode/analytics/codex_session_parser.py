from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from suitcode.analytics.codex_rollout_utils import (
    canonical_suitcode_tool_name,
    is_mcp_tool_name,
    iter_rollout_events,
    message_text_length,
    optional_non_empty,
    optional_resolved_path,
    parse_datetime,
    required_non_empty,
)
from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.native_agent_models import (
    CodexSessionAnalytics,
    CodexSessionArtifact,
    CodexSuitCodeToolUse,
    CodexTranscriptMetrics,
    CorrelationQuality,
    NativeAgentKind,
)


class CodexSessionParser:
    def parse(self, path: Path) -> CodexSessionAnalytics:
        artifact_path = path.expanduser().resolve()
        if not artifact_path.is_file():
            raise ValueError(f"Codex session artifact does not exist: `{artifact_path}`")

        session_meta: dict[str, object] | None = None
        last_event_at: datetime | None = None
        event_count = 0
        message_event_count = 0
        tool_event_count = 0
        assistant_message_count = 0
        user_message_count = 0
        mcp_tool_call_count = 0
        suitcode_tool_call_count = 0
        approx_input_characters = 0
        approx_output_characters = 0
        tool_order_index = 0
        first_suitcode_tool: str | None = None
        first_suitcode_tool_index: int | None = None
        first_high_value_suitcode_tool: str | None = None
        first_high_value_suitcode_tool_index: int | None = None
        tool_stats: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "first_seen_at": None, "last_seen_at": None})

        for line_number, event in iter_rollout_events(artifact_path):
            event_count += 1
            timestamp = self._parse_event_timestamp(event, artifact_path=artifact_path, line_number=line_number)
            last_event_at = timestamp

            event_type = event.get("type")
            if event_type == "session_meta":
                meta = event.get("payload")
                if not isinstance(meta, dict):
                    raise ValueError(f"invalid session_meta payload in `{artifact_path}` at line {line_number}")
                if session_meta is None:
                    session_meta = meta
                else:
                    self._validate_session_meta_consistency(session_meta, meta, artifact_path=artifact_path)
                continue

            if event_type != "response_item":
                continue

            payload = event.get("payload")
            if not isinstance(payload, dict):
                raise ValueError(f"invalid response_item payload in `{artifact_path}` at line {line_number}")
            payload_type = payload.get("type")

            if payload_type == "message":
                message_event_count += 1
                role = payload.get("role")
                content = payload.get("content")
                text_size = message_text_length(content)
                if role == "user":
                    user_message_count += 1
                    approx_input_characters += text_size
                elif role == "assistant":
                    assistant_message_count += 1
                    approx_output_characters += text_size
                continue

            if payload_type not in {"function_call", "custom_tool_call"}:
                continue

            tool_event_count += 1
            tool_order_index += 1
            name = payload.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"invalid tool call name in `{artifact_path}` at line {line_number}")
            normalized_name = name.strip()
            if is_mcp_tool_name(normalized_name):
                mcp_tool_call_count += 1
            suitcode_name = canonical_suitcode_tool_name(normalized_name)
            if suitcode_name is None:
                continue

            suitcode_tool_call_count += 1
            stats = tool_stats[suitcode_name]
            stats["count"] = int(stats["count"]) + 1
            if stats["first_seen_at"] is None:
                stats["first_seen_at"] = timestamp
            stats["last_seen_at"] = timestamp
            if first_suitcode_tool is None:
                first_suitcode_tool = suitcode_name
                first_suitcode_tool_index = tool_order_index
            if first_high_value_suitcode_tool is None and suitcode_name in HIGH_VALUE_TOOL_SET:
                first_high_value_suitcode_tool = suitcode_name
                first_high_value_suitcode_tool_index = tool_order_index

        if session_meta is None:
            raise ValueError(f"missing session_meta in `{artifact_path}`")
        session_id = required_non_empty(session_meta.get("id"), "session id", artifact_path)
        started_at = self._parse_meta_timestamp(session_meta, artifact_path=artifact_path)
        cwd = optional_resolved_path(session_meta.get("cwd"), artifact_path)
        repository_root = str(cwd) if cwd is not None else None
        cli_version = optional_non_empty(session_meta.get("cli_version"))
        model_provider = optional_non_empty(session_meta.get("model_provider"))
        if last_event_at is None:
            last_event_at = started_at

        suitcode_tools = tuple(
            CodexSuitCodeToolUse(
                tool_name=tool_name,
                call_count=int(stats["count"]),
                first_seen_at=stats["first_seen_at"],
                last_seen_at=stats["last_seen_at"],
            )
            for tool_name, stats in sorted(
                tool_stats.items(),
                key=lambda item: (item[1]["first_seen_at"], item[0]),
            )
        )
        return CodexSessionAnalytics(
            agent_kind=NativeAgentKind.CODEX,
            session_id=session_id,
            artifact=CodexSessionArtifact(
                session_id=session_id,
                artifact_path=str(artifact_path),
                repository_root=repository_root,
                started_at=started_at,
                last_event_at=last_event_at,
                cwd=(str(cwd) if cwd is not None else None),
                cli_version=cli_version,
                model_provider=model_provider,
                event_count=event_count,
            ),
            repository_root=repository_root,
            used_suitcode=bool(suitcode_tools),
            suitcode_tools=suitcode_tools,
            first_suitcode_tool=first_suitcode_tool,
            first_suitcode_tool_index=first_suitcode_tool_index,
            first_high_value_suitcode_tool=first_high_value_suitcode_tool,
            first_high_value_suitcode_tool_index=first_high_value_suitcode_tool_index,
            transcript_metrics=CodexTranscriptMetrics(
                event_count=event_count,
                message_event_count=message_event_count,
                tool_event_count=tool_event_count,
                assistant_message_count=assistant_message_count,
                user_message_count=user_message_count,
                mcp_tool_call_count=mcp_tool_call_count,
                suitcode_tool_call_count=suitcode_tool_call_count,
                approx_input_characters=approx_input_characters,
                approx_output_characters=approx_output_characters,
            ),
            correlation_quality=CorrelationQuality.NONE,
        )

    @staticmethod
    def _parse_event_timestamp(event: dict[str, object], *, artifact_path: Path, line_number: int) -> datetime:
        raw_timestamp = event.get("timestamp")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            raise ValueError(f"missing event timestamp in `{artifact_path}` at line {line_number}")
        return parse_datetime(raw_timestamp, artifact_path=artifact_path)

    @staticmethod
    def _parse_meta_timestamp(meta: dict[str, object], *, artifact_path: Path) -> datetime:
        raw_timestamp = meta.get("timestamp")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            raise ValueError(f"missing session timestamp in `{artifact_path}`")
        return parse_datetime(raw_timestamp, artifact_path=artifact_path)

    @staticmethod
    def _validate_session_meta_consistency(original: dict[str, object], candidate: dict[str, object], *, artifact_path: Path) -> None:
        for key in ("id", "cwd"):
            if original.get(key) != candidate.get(key):
                raise ValueError(f"inconsistent session_meta `{key}` in `{artifact_path}`")
