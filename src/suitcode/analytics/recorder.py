from __future__ import annotations

import atexit
from contextlib import contextmanager
from dataclasses import dataclass
import json
from datetime import UTC, datetime
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock
from time import perf_counter, time
from uuid import uuid4

from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.redaction import fingerprint_arguments, redact_arguments
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.token_economics import TokenEconomicsRecorder


@dataclass(frozen=True)
class _ActiveToolCall:
    invocation_id: str
    tool_name: str
    arguments: dict[str, object]
    repository_root: Path | None
    started_at_epoch_seconds: float
    started_perf_counter: float


class ToolCallRecorder:
    def __init__(
        self,
        store: JsonlAnalyticsStore,
        *,
        session_id: str | None = None,
        public_tool_profile: str | None = None,
    ) -> None:
        self._store = store
        self._session_id = session_id or f"session:{uuid4().hex}"
        self._benchmark_run_id: str | None = None
        self._benchmark_task_id: str | None = None
        self._env_task_id = _clean_env_value(os.getenv("SUITCODE_TASK_ID"))
        self._env_task_kind = _clean_env_value(os.getenv("SUITCODE_TASK_KIND"))
        self._env_study_kind = _clean_env_value(os.getenv("SUITCODE_STUDY_KIND"))
        self._token_economics = TokenEconomicsRecorder(public_tool_profile=public_tool_profile)
        self._lock = RLock()
        self._active_calls: dict[str, _ActiveToolCall] = {}
        atexit.register(self._flush_interrupted_at_exit)

    @property
    def analytics_run_id(self) -> str:
        return self._token_economics.analytics_run_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def store(self) -> JsonlAnalyticsStore:
        return self._store

    def set_benchmark_context(self, *, run_id: str, task_id: str) -> None:
        normalized_run_id = run_id.strip()
        normalized_task_id = task_id.strip()
        if not normalized_run_id or not normalized_task_id:
            raise ValueError("benchmark run_id and task_id must not be empty")
        self._benchmark_run_id = normalized_run_id
        self._benchmark_task_id = normalized_task_id

    def clear_benchmark_context(self) -> None:
        self._benchmark_run_id = None
        self._benchmark_task_id = None

    @contextmanager
    def benchmark_context(self, *, run_id: str, task_id: str):
        self.set_benchmark_context(run_id=run_id, task_id=task_id)
        try:
            yield
        finally:
            self.clear_benchmark_context()

    def record_success(
        self,
        *,
        invocation_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        result: object,
        duration_ms: int,
        started_at_epoch_seconds: float | None = None,
    ) -> AnalyticsEvent:
        self._clear_active_call(invocation_id)
        model_type, payload_bytes, payload_hash, item_count = _output_metadata(result)
        event = AnalyticsEvent(
            **self._base_event_fields(
                invocation_id=invocation_id,
                tool_name=tool_name,
                arguments=arguments,
                repository_root=repository_root,
            ),
            status=AnalyticsStatus.SUCCESS,
            duration_ms=duration_ms,
            output_model_type=model_type,
            output_payload_bytes=payload_bytes,
            output_payload_sha256=payload_hash,
            output_item_count=item_count,
        )
        self._store.append_event(event, repository_root=repository_root)
        if started_at_epoch_seconds is not None:
            self._token_economics.record_success(
                repository_root=repository_root,
                session_id=self._session_id,
                task_id=(self._benchmark_task_id or self._env_task_id),
                task_kind=self._env_task_kind,
                study_kind=self._env_study_kind,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                started_at=started_at_epoch_seconds,
                duration_ms=duration_ms,
            )
        return event

    def record_started(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        started_at_epoch_seconds: float | None = None,
        started_perf_counter: float | None = None,
    ) -> AnalyticsEvent:
        recorded_started_at_epoch_seconds = started_at_epoch_seconds if started_at_epoch_seconds is not None else time()
        recorded_started_perf_counter = started_perf_counter if started_perf_counter is not None else perf_counter()
        self._track_started_call(
            invocation_id=invocation_id,
            tool_name=tool_name,
            arguments=arguments,
            repository_root=repository_root,
            started_at_epoch_seconds=recorded_started_at_epoch_seconds,
            started_perf_counter=recorded_started_perf_counter,
        )
        event = AnalyticsEvent(
            **self._base_event_fields(
                invocation_id=invocation_id,
                tool_name=tool_name,
                arguments=arguments,
                repository_root=repository_root,
            ),
            status=AnalyticsStatus.STARTED,
            duration_ms=0,
        )
        self._store.append_event(event, repository_root=repository_root)
        return event

    def record_error(
        self,
        *,
        invocation_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        error: Exception,
        duration_ms: int,
        started_at_epoch_seconds: float | None = None,
    ) -> AnalyticsEvent:
        self._clear_active_call(invocation_id)
        event = AnalyticsEvent(
            **self._base_event_fields(
                invocation_id=invocation_id,
                tool_name=tool_name,
                arguments=arguments,
                repository_root=repository_root,
            ),
            status=AnalyticsStatus.ERROR,
            error_class=error.__class__.__name__,
            error_message=_truncate_error(str(error)),
            duration_ms=duration_ms,
        )
        self._store.append_event(event, repository_root=repository_root)
        if started_at_epoch_seconds is not None:
            self._token_economics.record_error(
                repository_root=repository_root,
                session_id=self._session_id,
                task_id=(self._benchmark_task_id or self._env_task_id),
                task_kind=self._env_task_kind,
                study_kind=self._env_study_kind,
                tool_name=tool_name,
                arguments=arguments,
                error=error,
                started_at=started_at_epoch_seconds,
                duration_ms=duration_ms,
            )
        return event

    def record_interrupted(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        duration_ms: int,
        started_at_epoch_seconds: float | None = None,
        reason: str = "interrupted before terminal completion",
    ) -> AnalyticsEvent:
        self._clear_active_call(invocation_id)
        message = _truncate_error(reason)
        event = AnalyticsEvent(
            **self._base_event_fields(
                invocation_id=invocation_id,
                tool_name=tool_name,
                arguments=arguments,
                repository_root=repository_root,
            ),
            status=AnalyticsStatus.INTERRUPTED,
            error_class="InterruptedToolCall",
            error_message=message,
            duration_ms=max(0, duration_ms),
        )
        self._store.append_event(event, repository_root=repository_root)
        if started_at_epoch_seconds is not None:
            self._token_economics.record_interrupted(
                repository_root=repository_root,
                session_id=self._session_id,
                task_id=(self._benchmark_task_id or self._env_task_id),
                task_kind=self._env_task_kind,
                study_kind=self._env_study_kind,
                tool_name=tool_name,
                arguments=arguments,
                started_at=started_at_epoch_seconds,
                duration_ms=max(0, duration_ms),
                reason=message,
            )
        return event

    def flush_interrupted_calls(self, *, reason: str = "process shutdown before terminal completion") -> tuple[AnalyticsEvent, ...]:
        with self._lock:
            active_calls = tuple(self._active_calls.values())
        flushed: list[AnalyticsEvent] = []
        current_perf_counter = perf_counter()
        for call in active_calls:
            duration_ms = int(max(0.0, current_perf_counter - call.started_perf_counter) * 1000)
            flushed.append(
                self.record_interrupted(
                    invocation_id=call.invocation_id,
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    repository_root=call.repository_root,
                    duration_ms=duration_ms,
                    started_at_epoch_seconds=call.started_at_epoch_seconds,
                    reason=reason,
                )
            )
        return tuple(flushed)

    def _base_event_fields(
        self,
        *,
        invocation_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
    ) -> dict[str, object]:
        arguments_redacted = redact_arguments(arguments)
        return {
            "event_id": f"event:{uuid4().hex}",
            "invocation_id": invocation_id,
            "session_id": self._session_id,
            "analytics_run_id": self._token_economics.analytics_run_id,
            "task_id": (self._benchmark_task_id or self._env_task_id),
            "task_kind": self._env_task_kind,
            "study_kind": self._env_study_kind,
            "benchmark_run_id": self._benchmark_run_id,
            "benchmark_task_id": self._benchmark_task_id,
            "timestamp_utc": _timestamp_utc(),
            "tool_name": tool_name,
            "workspace_id": _as_str_or_none(arguments.get("workspace_id")),
            "repository_id": _as_str_or_none(arguments.get("repository_id")),
            "repository_root": str(repository_root) if repository_root is not None else None,
            "arguments_redacted": arguments_redacted,
            "arguments_fingerprint_sha256": fingerprint_arguments(arguments_redacted),
        }

    def _track_started_call(
        self,
        *,
        invocation_id: str,
        tool_name: str,
        arguments: dict[str, object],
        repository_root: Path | None,
        started_at_epoch_seconds: float,
        started_perf_counter: float,
    ) -> None:
        with self._lock:
            self._active_calls[invocation_id] = _ActiveToolCall(
                invocation_id=invocation_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                repository_root=repository_root,
                started_at_epoch_seconds=started_at_epoch_seconds,
                started_perf_counter=started_perf_counter,
            )

    def _clear_active_call(self, invocation_id: str | None) -> None:
        if invocation_id is None:
            return
        with self._lock:
            self._active_calls.pop(invocation_id, None)

    def _flush_interrupted_at_exit(self) -> None:
        try:
            self.flush_interrupted_calls()
        except Exception:
            return


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


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


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
