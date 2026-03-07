from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.redaction import fingerprint_arguments, redact_arguments
from suitcode.analytics.storage import JsonlAnalyticsStore


class ToolCallRecorder:
    def __init__(
        self,
        store: JsonlAnalyticsStore,
        *,
        session_id: str | None = None,
    ) -> None:
        self._store = store
        self._session_id = session_id or f"session:{uuid4().hex}"

    def record_success(
        self,
        *,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        result: object,
        duration_ms: int,
    ) -> None:
        arguments_redacted = redact_arguments(arguments)
        args_fingerprint = fingerprint_arguments(arguments_redacted)
        model_type, payload_bytes, payload_hash, item_count = _output_metadata(result)
        event = AnalyticsEvent(
            event_id=f"event:{uuid4().hex}",
            session_id=self._session_id,
            timestamp_utc=_timestamp_utc(),
            tool_name=tool_name,
            workspace_id=_as_str_or_none(arguments.get("workspace_id")),
            repository_id=_as_str_or_none(arguments.get("repository_id")),
            repository_root=str(repository_root) if repository_root is not None else None,
            arguments_redacted=arguments_redacted,
            arguments_fingerprint_sha256=args_fingerprint,
            status=AnalyticsStatus.SUCCESS,
            duration_ms=duration_ms,
            output_model_type=model_type,
            output_payload_bytes=payload_bytes,
            output_payload_sha256=payload_hash,
            output_item_count=item_count,
        )
        self._store.append_event(event, repository_root=repository_root)

    def record_error(
        self,
        *,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        error: Exception,
        duration_ms: int,
    ) -> None:
        arguments_redacted = redact_arguments(arguments)
        args_fingerprint = fingerprint_arguments(arguments_redacted)
        event = AnalyticsEvent(
            event_id=f"event:{uuid4().hex}",
            session_id=self._session_id,
            timestamp_utc=_timestamp_utc(),
            tool_name=tool_name,
            workspace_id=_as_str_or_none(arguments.get("workspace_id")),
            repository_id=_as_str_or_none(arguments.get("repository_id")),
            repository_root=str(repository_root) if repository_root is not None else None,
            arguments_redacted=arguments_redacted,
            arguments_fingerprint_sha256=args_fingerprint,
            status=AnalyticsStatus.ERROR,
            error_class=error.__class__.__name__,
            error_message=_truncate_error(str(error)),
            duration_ms=duration_ms,
        )
        self._store.append_event(event, repository_root=repository_root)


def _timestamp_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _as_str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _truncate_error(value: str, max_chars: int = 400) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3] + "..."


def _output_metadata(result: object) -> tuple[str, int, str, int | None]:
    model_type = type(result).__name__
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")  # type: ignore[attr-defined]
    elif isinstance(result, tuple | list | dict):
        payload = result
    else:
        payload = repr(result)
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    payload_bytes = len(serialized.encode("utf-8"))
    payload_hash = sha256(serialized.encode("utf-8")).hexdigest()
    item_count: int | None = None
    if isinstance(result, tuple | list):
        item_count = len(result)
    elif hasattr(result, "items"):
        items = getattr(result, "items")
        if isinstance(items, tuple | list):
            item_count = len(items)
    return model_type, payload_bytes, payload_hash, item_count

