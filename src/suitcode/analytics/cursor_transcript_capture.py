from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from suitcode.analytics.cursor_session_store import CursorSessionStore
from suitcode.analytics.tool_naming import canonical_suitcode_tool_name, is_mcp_tool_name
from suitcode.analytics.transcript_models import TranscriptCapture, TranscriptSegment, TranscriptSegmentKind


class CursorTranscriptCaptureBuilder:
    def __init__(self, store: CursorSessionStore | None = None) -> None:
        self._store = store or CursorSessionStore()

    def build(self, path: Path) -> TranscriptCapture:
        artifact_path = path.expanduser().resolve()
        if not artifact_path.is_file():
            raise ValueError(f'Cursor session artifact does not exist: `{artifact_path}`')
        meta = self._store.session_meta(artifact_path)
        session_id = str(meta['session_id'])
        repository_root = str(meta['cwd']) if meta['cwd'] is not None else None
        sequence_index = 0
        segments: list[TranscriptSegment] = []
        call_index: dict[str, tuple[str, bool, bool, str | None]] = {}

        with artifact_path.open('r', encoding='utf-8') as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f'invalid Cursor event object in `{artifact_path}` at line {line_number}')
                timestamp = self._timestamp_text(payload, artifact_path, default_index=line_number)
                role = payload.get('role')
                message = payload.get('message')
                if role not in {'user', 'assistant'} or not isinstance(message, dict):
                    continue
                content = message.get('content')
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get('type')
                    if block_type == 'text':
                        text = block.get('text')
                        if not isinstance(text, str) or not text:
                            continue
                        sequence_index += 1
                        kind = TranscriptSegmentKind.USER_MESSAGE if role == 'user' else TranscriptSegmentKind.ASSISTANT_MESSAGE
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=kind,
                                role=role,
                                content_text=text,
                                content_bytes=len(text.encode('utf-8')),
                            )
                        )
                    elif block_type == 'tool_use' and role == 'assistant':
                        name = block.get('name')
                        if not isinstance(name, str) or not name.strip():
                            continue
                        tool_name = name.strip()
                        server_name = block.get('server_name') if isinstance(block.get('server_name'), str) else None
                        canonical_name = canonical_suitcode_tool_name(tool_name, server_name=server_name)
                        call_id = block.get('id') if isinstance(block.get('id'), str) and block.get('id').strip() else f'{session_id}:call:{sequence_index + 1}'
                        arguments_text = json.dumps(block.get('input'), ensure_ascii=True, sort_keys=True)
                        content_text = f'tool:{tool_name}\narguments:{arguments_text}'
                        sequence_index += 1
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=TranscriptSegmentKind.MCP_TOOL_CALL if is_mcp_tool_name(tool_name) else TranscriptSegmentKind.CUSTOM_TOOL_CALL,
                                tool_name=tool_name,
                                content_text=content_text,
                                content_bytes=len(content_text.encode('utf-8')),
                                metadata={'call_id': call_id, 'arguments_text': arguments_text},
                                is_mcp=is_mcp_tool_name(tool_name),
                                is_suitcode=canonical_name is not None,
                                canonical_tool_name=canonical_name,
                            )
                        )
                        call_index[call_id] = (tool_name, is_mcp_tool_name(tool_name), canonical_name is not None, canonical_name)
                    elif block_type == 'tool_result':
                        call_id = block.get('tool_use_id') if isinstance(block.get('tool_use_id'), str) else None
                        if call_id is None or call_id not in call_index:
                            continue
                        tool_name, is_mcp, is_suitcode, canonical_name = call_index[call_id]
                        output_text = self._tool_result_text(block.get('content'))
                        content_text = f'tool:{tool_name}\noutput:{output_text}'
                        sequence_index += 1
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=TranscriptSegmentKind.MCP_TOOL_OUTPUT if is_mcp else TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT,
                                tool_name=tool_name,
                                content_text=content_text,
                                content_bytes=len(content_text.encode('utf-8')),
                                metadata={'call_id': call_id, 'output_text': output_text},
                                is_mcp=is_mcp,
                                is_suitcode=is_suitcode,
                                canonical_tool_name=canonical_name,
                            )
                        )

        return TranscriptCapture(
            session_id=session_id,
            repository_root=repository_root,
            artifact_path=str(artifact_path),
            segments=tuple(segments),
        )

    @staticmethod
    def _timestamp_text(payload: dict[str, object], artifact_path: Path, *, default_index: int) -> str:
        raw = payload.get('timestamp')
        if isinstance(raw, str) and raw.strip():
            normalized = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
            return datetime.fromisoformat(normalized).astimezone(UTC).isoformat().replace('+00:00', 'Z')
        base = datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC)
        return base.replace(microsecond=min(default_index, 999999)).isoformat().replace('+00:00', 'Z')

    @staticmethod
    def _tool_result_text(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            chunks: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get('text')
                    if isinstance(text, str) and text:
                        chunks.append(text)
                elif isinstance(item, str) and item:
                    chunks.append(item)
            if chunks:
                return '\n'.join(chunks)
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
