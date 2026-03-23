from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOL_SET
from suitcode.analytics.native_agent_models import (
    CorrelationQuality,
    NativeAgentKind,
    NativeSessionAnalytics,
    NativeSessionArtifact,
    NativeSuitCodeToolUse,
    NativeTranscriptMetrics,
)
from suitcode.analytics.tool_naming import canonical_suitcode_tool_name, is_mcp_tool_name
from suitcode.analytics.cursor_session_store import CursorSessionStore


class CursorSessionParser:
    def __init__(self, store: CursorSessionStore | None = None) -> None:
        self._store = store or CursorSessionStore()

    def parse(self, path: Path) -> NativeSessionAnalytics:
        artifact_path = path.expanduser().resolve()
        if not artifact_path.is_file():
            raise ValueError(f'Cursor session artifact does not exist: `{artifact_path}`')
        artifact_stat = artifact_path.stat()
        created_at = datetime.fromtimestamp(artifact_stat.st_ctime, tz=UTC)
        modified_at = datetime.fromtimestamp(artifact_stat.st_mtime, tz=UTC)

        meta = self._store.session_meta(artifact_path)
        session_id = str(meta['session_id'])
        repository_root = str(meta['cwd']) if meta['cwd'] is not None else None
        started_at: datetime | None = None
        last_event_at: datetime | None = None
        saw_explicit_timestamp = False
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
        tool_stats: dict[str, dict[str, object]] = defaultdict(lambda: {'count': 0, 'first_seen_at': None, 'last_seen_at': None})

        with artifact_path.open('r', encoding='utf-8') as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f'invalid Cursor event object in `{artifact_path}` at line {line_number}')
                event_count += 1
                raw_timestamp = payload.get('timestamp')
                if isinstance(raw_timestamp, str) and raw_timestamp.strip():
                    saw_explicit_timestamp = True
                timestamp = self._parse_timestamp(payload, modified_at, default_index=line_number)
                if started_at is None:
                    started_at = timestamp
                last_event_at = timestamp

                role = payload.get('role')
                if role not in {'user', 'assistant'}:
                    continue
                message = payload.get('message')
                if not isinstance(message, dict):
                    continue
                content = message.get('content')
                if not isinstance(content, list):
                    continue
                message_event_count += 1
                if role == 'user':
                    user_message_count += 1
                else:
                    assistant_message_count += 1
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get('type')
                    if block_type == 'text':
                        text = block.get('text')
                        if isinstance(text, str):
                            if role == 'user':
                                approx_input_characters += len(text)
                            else:
                                approx_output_characters += len(text)
                    elif block_type == 'tool_use' and role == 'assistant':
                        tool_event_count += 1
                        tool_order_index += 1
                        name = block.get('name')
                        if not isinstance(name, str) or not name.strip():
                            continue
                        tool_name = name.strip()
                        server_name = block.get('server_name') if isinstance(block.get('server_name'), str) else None
                        canonical_name = canonical_suitcode_tool_name(tool_name, server_name=server_name)
                        if is_mcp_tool_name(tool_name):
                            mcp_tool_call_count += 1
                        if canonical_name is not None:
                            suitcode_tool_call_count += 1
                            stats = tool_stats[canonical_name]
                            stats['count'] = int(stats['count']) + 1
                            if stats['first_seen_at'] is None:
                                stats['first_seen_at'] = timestamp
                            stats['last_seen_at'] = timestamp
                            if first_suitcode_tool is None:
                                first_suitcode_tool = canonical_name
                                first_suitcode_tool_index = tool_order_index
                            if first_high_value_suitcode_tool is None and canonical_name in HIGH_VALUE_TOOL_SET:
                                first_high_value_suitcode_tool = canonical_name
                                first_high_value_suitcode_tool_index = tool_order_index

        if started_at is None:
            started_at = created_at
        if last_event_at is None:
            last_event_at = modified_at
        if not saw_explicit_timestamp:
            started_at = created_at
            last_event_at = modified_at

        suitcode_tools = tuple(
            NativeSuitCodeToolUse(
                tool_name=tool_name,
                call_count=int(stats['count']),
                first_seen_at=stats['first_seen_at'],
                last_seen_at=stats['last_seen_at'],
            )
            for tool_name, stats in sorted(tool_stats.items(), key=lambda item: (item[1]['first_seen_at'], item[0]))
        )
        return NativeSessionAnalytics(
            agent_kind=NativeAgentKind.CURSOR,
            session_id=session_id,
            artifact=NativeSessionArtifact(
                session_id=session_id,
                artifact_path=str(artifact_path),
                repository_root=repository_root,
                started_at=started_at,
                last_event_at=last_event_at,
                cwd=repository_root,
                cli_version=None,
                model_provider='cursor',
                event_count=event_count,
            ),
            repository_root=repository_root,
            used_suitcode=bool(suitcode_tools),
            suitcode_tools=suitcode_tools,
            first_suitcode_tool=first_suitcode_tool,
            first_suitcode_tool_index=first_suitcode_tool_index,
            first_high_value_suitcode_tool=first_high_value_suitcode_tool,
            first_high_value_suitcode_tool_index=first_high_value_suitcode_tool_index,
            transcript_metrics=NativeTranscriptMetrics(
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
    def _parse_timestamp(payload: dict[str, object], fallback_base: datetime, *, default_index: int) -> datetime:
        raw = payload.get('timestamp')
        if isinstance(raw, str) and raw.strip():
            normalized = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
            return datetime.fromisoformat(normalized).astimezone(UTC)
        return fallback_base.replace(microsecond=min(default_index, 999999))
