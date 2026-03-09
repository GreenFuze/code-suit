from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


MCP_PREFIXES = ("mcp__", "functions.mcp__")
SUITCODE_PREFIXES = ("mcp__suitcode__", "functions.mcp__suitcode__")


def iter_rollout_events(path: Path):
    artifact_path = path.expanduser().resolve()
    if not artifact_path.is_file():
        raise ValueError(f"Codex session artifact does not exist: `{artifact_path}`")
    with artifact_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in `{artifact_path}` at line {line_number}") from exc
            if not isinstance(event, dict):
                raise ValueError(f"invalid event object in `{artifact_path}` at line {line_number}")
            yield line_number, event


def parse_datetime(value: str, *, artifact_path: Path) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC)


def required_non_empty(value: object, label: str, artifact_path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid {label} in `{artifact_path}`")
    return value.strip()


def optional_non_empty(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def optional_resolved_path(value: object, artifact_path: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid session cwd in `{artifact_path}`")
    return Path(value).expanduser().resolve()


def message_text(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text")
        if isinstance(raw_text, str) and raw_text:
            parts.append(raw_text)
    return "\n".join(parts)


def message_text_length(content: object) -> int:
    return len(message_text(content))


def is_mcp_tool_name(tool_name: str) -> bool:
    return tool_name.startswith(MCP_PREFIXES)


def canonical_suitcode_tool_name(tool_name: str) -> str | None:
    for prefix in SUITCODE_PREFIXES:
        if tool_name.startswith(prefix):
            suffix = tool_name[len(prefix) :].strip()
            if not suffix:
                raise ValueError(f"invalid SuitCode tool name `{tool_name}`")
            return suffix
    return None
