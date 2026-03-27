from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from suitcode.analytics.tool_naming import canonical_suitcode_tool_name, is_mcp_tool_name
from suitcode.analytics.transcript_models import TranscriptCapture, TranscriptSegment, TranscriptSegmentKind


class ClaudeTranscriptCaptureBuilder:
    def build(self, path: Path) -> TranscriptCapture:
        artifact_path = path.expanduser().resolve()
        if not artifact_path.is_file():
            raise ValueError(f'Claude session artifact does not exist: `{artifact_path}`')

        session_id: str | None = None
        repository_root: str | None = None
        sequence_index = 0
        call_index: dict[str, tuple[str, bool, bool, str | None]] = {}
        segments: list[TranscriptSegment] = []

        with artifact_path.open('r', encoding='utf-8') as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError(f'invalid Claude event object in `{artifact_path}` at line {line_number}')
                if session_id is None:
                    raw_session_id = payload.get('sessionId')
                    if isinstance(raw_session_id, str) and raw_session_id.strip():
                        session_id = raw_session_id.strip()
                    else:
                        session_id = artifact_path.stem
                if repository_root is None:
                    raw_cwd = payload.get('cwd')
                    if isinstance(raw_cwd, str) and raw_cwd.strip():
                        repository_root = str(Path(raw_cwd).expanduser().resolve())
                timestamp = self._timestamp_text(payload, artifact_path)
                message = payload.get('message')
                if not isinstance(message, dict):
                    continue
                role = message.get('role')
                content = message.get('content')
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get('type')
                    if block_type == 'text':
                        text = block.get('text')
                        if not isinstance(text, str) or not text.strip():
                            continue
                        kind = TranscriptSegmentKind.USER_MESSAGE if role == 'user' else TranscriptSegmentKind.ASSISTANT_MESSAGE
                        sequence_index += 1
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=kind,
                                role=role if isinstance(role, str) else None,
                                content_text=text,
                                content_bytes=len(text.encode('utf-8')),
                            )
                        )
                    elif block_type == 'tool_use' and role == 'assistant':
                        name = block.get('name')
                        if not isinstance(name, str) or not name.strip():
                            raise ValueError(f'invalid Claude tool name in `{artifact_path}` at line {line_number}')
                        tool_name = name.strip()
                        server_name = block.get('server_name') if isinstance(block.get('server_name'), str) else None
                        canonical_name = canonical_suitcode_tool_name(tool_name, server_name=server_name)
                        call_id = block.get('id') if isinstance(block.get('id'), str) and block.get('id').strip() else f'{session_id}:call:{sequence_index + 1}'
                        input_text = json.dumps(block.get('input'), ensure_ascii=True, sort_keys=True)
                        sequence_index += 1
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=TranscriptSegmentKind.MCP_TOOL_CALL if is_mcp_tool_name(tool_name) else TranscriptSegmentKind.CUSTOM_TOOL_CALL,
                                tool_name=tool_name,
                                content_text=f'tool:{tool_name}\narguments:{input_text}',
                                content_bytes=len(f'tool:{tool_name}\narguments:{input_text}'.encode('utf-8')),
                                metadata={'call_id': call_id, 'arguments_text': input_text},
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
                        if not output_text.strip():
                            continue
                        kind = TranscriptSegmentKind.MCP_TOOL_OUTPUT if is_mcp else TranscriptSegmentKind.CUSTOM_TOOL_OUTPUT
                        sequence_index += 1
                        segments.append(
                            TranscriptSegment(
                                segment_id=f'{session_id}:segment:{sequence_index}',
                                session_id=session_id,
                                sequence_index=sequence_index,
                                timestamp_utc=timestamp,
                                kind=kind,
                                tool_name=tool_name,
                                content_text=f'tool:{tool_name}\noutput:{output_text}',
                                content_bytes=len(f'tool:{tool_name}\noutput:{output_text}'.encode('utf-8')),
                                metadata={'call_id': call_id, 'output_text': output_text},
                                is_mcp=is_mcp,
                                is_suitcode=is_suitcode,
                                canonical_tool_name=canonical_name,
                            )
                        )

        if session_id is None:
            session_id = artifact_path.stem
        return TranscriptCapture(
            session_id=session_id,
            repository_root=repository_root,
            artifact_path=str(artifact_path),
            segments=tuple(segments),
        )

    @staticmethod
    def _timestamp_text(payload: dict[str, object], artifact_path: Path) -> str:
        raw = payload.get('timestamp')
        if not isinstance(raw, str) or not raw.strip():
            return datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC).isoformat().replace('+00:00', 'Z')
        normalized = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
        return datetime.fromisoformat(normalized).astimezone(UTC).isoformat().replace('+00:00', 'Z')

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
