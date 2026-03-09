from __future__ import annotations

from collections import Counter
from pathlib import Path

from suitcode.analytics.high_value_tools import HIGH_VALUE_TOOLS
from suitcode.analytics.models import AnalyticsEvent, BenchmarkArtifactReference, BenchmarkTaskResult
from suitcode.analytics.benchmark_harness import BenchmarkTaskRun

_ARTIFACT_KEY_TO_KIND = {
    "codex_session_artifact": "codex_session_artifact",
    "claude_telemetry_reference": "claude_telemetry_reference",
    "cursor_run_metadata": "cursor_run_metadata",
}


class BenchmarkProvenanceScanner:
    def scan(self, *roots: object) -> tuple[dict[str, int], dict[str, int]]:
        confidence_mix: Counter[str] = Counter()
        source_kind_mix: Counter[str] = Counter()
        visited: set[int] = set()
        for root in roots:
            self._walk(root, visited=visited, confidence_mix=confidence_mix, source_kind_mix=source_kind_mix)
        return dict(confidence_mix), dict(source_kind_mix)

    def _walk(
        self,
        value: object,
        *,
        visited: set[int],
        confidence_mix: Counter[str],
        source_kind_mix: Counter[str],
    ) -> None:
        if value is None or isinstance(value, (str, int, float, bool)):
            return
        if isinstance(value, dict):
            for item in value.values():
                self._walk(item, visited=visited, confidence_mix=confidence_mix, source_kind_mix=source_kind_mix)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                self._walk(item, visited=visited, confidence_mix=confidence_mix, source_kind_mix=source_kind_mix)
            return
        object_id = id(value)
        if object_id in visited:
            return
        visited.add(object_id)
        provenance = getattr(value, "provenance", None)
        if provenance is not None:
            self._scan_provenance_items(provenance, confidence_mix=confidence_mix, source_kind_mix=source_kind_mix)
        fields = getattr(value, "model_fields", None)
        if isinstance(fields, dict):
            for field_name in fields:
                if field_name == "provenance":
                    continue
                self._walk(
                    getattr(value, field_name, None),
                    visited=visited,
                    confidence_mix=confidence_mix,
                    source_kind_mix=source_kind_mix,
                )
            return
        if hasattr(value, "__dict__"):
            for field_name, item in vars(value).items():
                if field_name == "provenance":
                    continue
                self._walk(item, visited=visited, confidence_mix=confidence_mix, source_kind_mix=source_kind_mix)

    @staticmethod
    def _scan_provenance_items(
        items: object,
        *,
        confidence_mix: Counter[str],
        source_kind_mix: Counter[str],
    ) -> None:
        if not isinstance(items, (tuple, list)):
            return
        for item in items:
            if isinstance(item, dict):
                confidence_mode = item.get("confidence_mode")
                source_kind = item.get("source_kind")
            else:
                confidence_mode = getattr(item, "confidence_mode", None)
                source_kind = getattr(item, "source_kind", None)
            confidence_value = _enum_or_str_value(confidence_mode)
            source_kind_value = _enum_or_str_value(source_kind)
            if not confidence_value or not source_kind_value:
                raise ValueError("recognized provenance items must define non-empty confidence_mode and source_kind")
            confidence_mix[confidence_value] += 1
            source_kind_mix[source_kind_value] += 1


class BenchmarkTelemetryCollector:
    def __init__(self) -> None:
        self._provenance_scanner = BenchmarkProvenanceScanner()

    def collect_task_run(
        self,
        *,
        run_id: str,
        task: dict[str, object],
        task_artifact_path: Path,
        repository_root: Path,
        session_id: str,
        workspace_id: str | None,
        repository_id: str | None,
        tool_calls: int,
        duration_ms: int,
        execution,
        store,
        truth_coverage: object | None = None,
    ) -> BenchmarkTaskRun:
        task_id = _required_string(task, "task_id")
        events = tuple(
            item
            for item in store.load_events(repository_root=repository_root, include_global=True)
            if item.benchmark_run_id == run_id and item.benchmark_task_id == task_id
        )
        if tool_calls > 0 and not events:
            raise ValueError(f"benchmark task `{task_id}` produced tool calls but no correlated analytics events")
        event_session_ids = {item.session_id for item in events}
        if events and event_session_ids != {session_id}:
            raise ValueError(f"benchmark task `{task_id}` correlated to unexpected analytics sessions")
        event_repository_roots = {item.repository_root for item in events if item.repository_root is not None}
        if any(item != str(repository_root) for item in event_repository_roots):
            raise ValueError(f"benchmark task `{task_id}` correlated to conflicting repository roots")
        if tool_calls != len(events):
            raise ValueError(
                f"benchmark task `{task_id}` recorded {tool_calls} tool calls but correlated {len(events)} analytics events"
            )
        first_tool, first_index = self._first_high_value_tool(events)
        confidence_mix, source_kind_mix = self._provenance_scanner.scan(*execution.outputs)
        artifact_references = self._artifact_references(
            task=task,
            task_artifact_path=task_artifact_path,
            store=store,
        )
        result = BenchmarkTaskResult(
            task_id=task_id,
            status=execution.status,
            tool_calls=tool_calls,
            turn_count=len(events),
            duration_ms=duration_ms,
            session_id=session_id,
            workspace_id=workspace_id,
            repository_id=repository_id,
            repository_root=str(repository_root),
            first_high_value_tool=first_tool,
            first_high_value_tool_call_index=first_index,
            used_high_value_tool_early=(first_index is not None and first_index <= 3),
            deterministic_action_kind=execution.deterministic_action_kind,
            deterministic_action_target_id=execution.deterministic_action_target_id,
            deterministic_action_status=execution.deterministic_action_status,
            provenance_confidence_mix=confidence_mix,
            provenance_source_kind_mix=source_kind_mix,
            artifact_references=artifact_references,
            notes=execution.note,
        )
        metadata = {
            "task": _json_ready(task),
            "result": result.model_dump(mode="json"),
            "event_ids": [item.event_id for item in events],
            "tool_names": [item.tool_name for item in events],
            "benchmark_run_id": run_id,
            "benchmark_task_id": task_id,
            "truth_coverage": _json_ready(truth_coverage),
        }
        return BenchmarkTaskRun(result=result, metadata=metadata)

    @staticmethod
    def _first_high_value_tool(events: tuple[AnalyticsEvent, ...]) -> tuple[str | None, int | None]:
        for index, event in enumerate(events, start=1):
            if event.tool_name in HIGH_VALUE_TOOLS:
                return event.tool_name, index
        return None, None

    @staticmethod
    def _artifact_references(*, task: dict[str, object], task_artifact_path: Path, store) -> tuple[BenchmarkArtifactReference, ...]:
        references = [
            BenchmarkArtifactReference(
                kind="benchmark_task_metadata",
                location=str(task_artifact_path),
                description="benchmark task metadata and correlated event IDs",
            )
        ]
        global_stream = store.global_root() / "events" / "active.jsonl"
        references.append(
            BenchmarkArtifactReference(
                kind="analytics_event_stream",
                location=str(global_stream),
                description="global analytics event stream active file",
            )
        )
        for key, kind in _ARTIFACT_KEY_TO_KIND.items():
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                references.append(BenchmarkArtifactReference(kind=kind, location=value.strip()))
        return tuple(references)


def _required_string(task: dict[str, object], key: str) -> str:
    value = task.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"benchmark task missing non-empty `{key}`")
    return value.strip()


def _enum_or_str_value(value: object) -> str | None:
    if value is None:
        return None
    candidate = getattr(value, "value", value)
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[attr-defined]
    if hasattr(value, "__dict__"):
        return {key: _json_ready(item) for key, item in vars(value).items()}
    return str(value)
