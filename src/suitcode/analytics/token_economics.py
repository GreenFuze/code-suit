from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

import tiktoken
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TOKEN_ECONOMICS_SCHEMA_VERSION = "token_economics.v1"
TOKEN_ECONOMICS_SCOPE = "file_backed_evidence_lower_bound_v1"
TOKEN_ECONOMICS_TOOL_NAMES = frozenset(
    {
        "understand_repository",
        "understand_file",
        "what_changes_if_i_edit_this",
        "what_should_i_run",
        "what_is_not_proven",
    }
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenizerInfo(StrictModel):
    name: str
    version: str | None = None


class TokenEconomicsEvidenceItem(StrictModel):
    evidence_id: str
    kind: str
    path: str | None = None
    span: str | None = None
    content_hash: str | None = None
    token_count: int
    included_in_response: bool = False


class TokenEconomicsEvent(StrictModel):
    schema_version: str = TOKEN_ECONOMICS_SCHEMA_VERSION
    project_root: str
    project_id: str
    session_id: str
    task_id: str | None = None
    tool_call_id: str
    tool_name: str
    detail_level: str | None = None
    started_at: str
    finished_at: str
    elapsed_ms: int
    status: str
    error_class: str | None = None
    error_message: str | None = None
    tokenizer: TokenizerInfo
    evidence_scope: str = TOKEN_ECONOMICS_SCOPE
    response_tokens: int = 0
    evidence_footprint_tokens: int = 0
    unique_session_evidence_tokens: int = 0
    duplicate_session_evidence_tokens: int = 0
    evidence_token_reduction_pct: float = 0.0
    session_marginal_reduction_pct: float = 0.0
    session_marginal_reduction_interpretable: bool = False
    evidence_item_count: int = 0
    deduped_session_evidence_item_count: int = 0
    targets: tuple[str, ...] = Field(default_factory=tuple)
    evidence_items: tuple[TokenEconomicsEvidenceItem, ...] = Field(default_factory=tuple)

    @field_validator("started_at", "finished_at")
    @classmethod
    def _validate_utc_timestamp(cls, value: str) -> str:
        if not value.endswith("Z"):
            raise ValueError("timestamp must be UTC ISO-8601 with Z suffix")
        datetime.fromisoformat(value[:-1] + "+00:00")
        return value

    @model_validator(mode="after")
    def _validate_counts(self) -> "TokenEconomicsEvent":
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be >= 0")
        for field_name in (
            "response_tokens",
            "evidence_footprint_tokens",
            "unique_session_evidence_tokens",
            "duplicate_session_evidence_tokens",
            "evidence_item_count",
            "deduped_session_evidence_item_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if self.status == "success" and (self.error_class is not None or self.error_message is not None):
            raise ValueError("success token-economics events must not include error fields")
        if self.status != "success" and not self.error_class:
            raise ValueError("non-success token-economics events must include error_class")
        return self


class TokenEconomicsAggregate(StrictModel):
    name: str
    event_count: int
    success_count: int
    failure_count: int
    total_elapsed_ms: int
    avg_elapsed_ms: float
    p50_elapsed_ms: int
    p95_elapsed_ms: int
    max_elapsed_ms: int
    total_response_tokens: int
    total_evidence_footprint_tokens: int
    unique_evidence_tokens: int
    duplicate_evidence_tokens: int
    evidence_token_reduction_pct: float
    session_unique_evidence_reduction_pct: float
    status_counts: dict[str, int]
    tool_counts: dict[str, int]


class TokenEconomicsReport(StrictModel):
    schema_version: str = TOKEN_ECONOMICS_SCHEMA_VERSION
    generated_at: str
    workspace: str
    include_failures: bool
    ignored_event_count: int
    total: TokenEconomicsAggregate
    by_session: tuple[TokenEconomicsAggregate, ...]
    by_day: tuple[TokenEconomicsAggregate, ...]
    by_tool: tuple[TokenEconomicsAggregate, ...]


@dataclass(frozen=True)
class _SerializedResult:
    payload: Any
    text: str


class TokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.name = encoding_name
        self.version = getattr(tiktoken, "__version__", None)
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def info(self) -> TokenizerInfo:
        return TokenizerInfo(name=self.name, version=self.version)


class TokenEconomicsStore:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._root = self._repository_root / ".suit" / "analytics" / "token-economics"
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def events_file(self) -> Path:
        return self._root / "events.jsonl"

    def append_event(self, event: TokenEconomicsEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            self._write_schema_file()
            with self.events_file.open("ab") as handle:
                handle.write((line + "\n").encode("utf-8"))

    def load_events(self) -> tuple[TokenEconomicsEvent, ...]:
        if not self.events_file.exists():
            return tuple()
        events: list[TokenEconomicsEvent] = []
        with self._lock:
            for raw_line in self.events_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                events.append(TokenEconomicsEvent.model_validate_json(line))
        return tuple(sorted(events, key=lambda item: (item.started_at, item.tool_call_id)))

    def _write_schema_file(self) -> None:
        schema_file = self._root / "schema.json"
        if schema_file.exists():
            return
        schema = {
            "schema_version": TOKEN_ECONOMICS_SCHEMA_VERSION,
            "evidence_scope": TOKEN_ECONOMICS_SCOPE,
            "description": (
                "Deterministic token-economics telemetry. Evidence footprint is a "
                "file-backed lower bound derived from public SuitCode evidence references."
            ),
            "metrics": {
                "response_tokens": "Tokens in the serialized public MCP success payload.",
                "evidence_footprint_tokens": "Tokens in file-backed evidence items attributed to the call before session dedupe.",
                "unique_session_evidence_tokens": "Tokens in evidence items not previously seen in the same session.",
                "duplicate_session_evidence_tokens": "Evidence tokens already seen earlier in the same session.",
                "evidence_token_reduction_pct": "100 * (1 - response_tokens / evidence_footprint_tokens).",
                "session_marginal_reduction_pct": "100 * (1 - response_tokens / unique_session_evidence_tokens).",
            },
        }
        schema_file.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TokenEconomicsRecorder:
    def __init__(self, *, counter: TokenCounter | None = None) -> None:
        self._counter = counter or TokenCounter()

    def record_success(
        self,
        *,
        repository_root: Path | None,
        session_id: str,
        task_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        result: object,
        started_at: float,
        duration_ms: int,
    ) -> TokenEconomicsEvent | None:
        if repository_root is None or tool_name not in TOKEN_ECONOMICS_TOOL_NAMES:
            return None
        repository_root = repository_root.expanduser().resolve()
        serialized = _serialize_result(result)
        response_tokens = self._counter.count_text(serialized.text)
        evidence_items = self._collect_evidence_items(repository_root, serialized.payload)
        return self._record(
            repository_root=repository_root,
            session_id=session_id,
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            started_at=started_at,
            duration_ms=duration_ms,
            status="success",
            response_tokens=response_tokens,
            evidence_items=evidence_items,
        )

    def record_error(
        self,
        *,
        repository_root: Path | None,
        session_id: str,
        task_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        error: Exception,
        started_at: float,
        duration_ms: int,
    ) -> TokenEconomicsEvent | None:
        if repository_root is None or tool_name not in TOKEN_ECONOMICS_TOOL_NAMES:
            return None
        return self._record(
            repository_root=repository_root.expanduser().resolve(),
            session_id=session_id,
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            started_at=started_at,
            duration_ms=duration_ms,
            status="error",
            error_class=error.__class__.__name__,
            error_message=_truncate_error(str(error)),
            response_tokens=0,
            evidence_items=tuple(),
        )

    def _record(
        self,
        *,
        repository_root: Path,
        session_id: str,
        task_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        started_at: float,
        duration_ms: int,
        status: str,
        response_tokens: int,
        evidence_items: tuple[TokenEconomicsEvidenceItem, ...],
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> TokenEconomicsEvent:
        store = TokenEconomicsStore(repository_root)
        previous_events = store.load_events()
        seen_ids = {
            item.evidence_id
            for event in previous_events
            if event.session_id == session_id
            for item in event.evidence_items
        }
        unique_items = tuple(item for item in evidence_items if item.evidence_id not in seen_ids)
        evidence_footprint_tokens = sum(item.token_count for item in evidence_items)
        unique_session_evidence_tokens = sum(item.token_count for item in unique_items)
        duplicate_session_evidence_tokens = max(0, evidence_footprint_tokens - unique_session_evidence_tokens)
        started = datetime.fromtimestamp(started_at, UTC)
        finished = datetime.fromtimestamp(started_at + (duration_ms / 1000), UTC)
        event = TokenEconomicsEvent(
            project_root=str(repository_root),
            project_id=_project_id(repository_root),
            session_id=session_id,
            task_id=task_id,
            tool_call_id=f"toolcall:{uuid4().hex}",
            tool_name=tool_name,
            detail_level=_detail_level(arguments),
            started_at=_timestamp(started),
            finished_at=_timestamp(finished),
            elapsed_ms=duration_ms,
            status=status,
            error_class=error_class,
            error_message=error_message,
            tokenizer=self._counter.info(),
            response_tokens=response_tokens,
            evidence_footprint_tokens=evidence_footprint_tokens,
            unique_session_evidence_tokens=unique_session_evidence_tokens,
            duplicate_session_evidence_tokens=duplicate_session_evidence_tokens,
            evidence_token_reduction_pct=_pct_reduction(response_tokens, evidence_footprint_tokens),
            session_marginal_reduction_pct=_pct_reduction(response_tokens, unique_session_evidence_tokens),
            session_marginal_reduction_interpretable=unique_session_evidence_tokens >= response_tokens > 0,
            evidence_item_count=len(evidence_items),
            deduped_session_evidence_item_count=len(unique_items),
            targets=_targets(arguments),
            evidence_items=evidence_items,
        )
        store.append_event(event)
        return event

    def _collect_evidence_items(self, repository_root: Path, payload: Any) -> tuple[TokenEconomicsEvidenceItem, ...]:
        references = _collect_path_references(payload)
        items: dict[str, TokenEconomicsEvidenceItem] = {}
        for reference in references:
            item = self._evidence_item_for_reference(repository_root, reference)
            if item is not None:
                items[item.evidence_id] = item
        return tuple(sorted(items.values(), key=lambda item: item.evidence_id))

    def _evidence_item_for_reference(
        self,
        repository_root: Path,
        reference: "_PathReference",
    ) -> TokenEconomicsEvidenceItem | None:
        if _looks_external(reference.path):
            return None
        rel_path = _normalize_path(reference.path)
        candidate = repository_root / Path(*rel_path.split("/"))
        if not candidate.is_file():
            return None
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        evidence_text, normalized_span = _slice_text(text, reference.span)
        content_hash = sha256(evidence_text.encode("utf-8", errors="replace")).hexdigest()
        token_count = self._counter.count_text(evidence_text)
        evidence_id = f"file-span:{rel_path}:{normalized_span or 'all'}:sha256:{content_hash}"
        return TokenEconomicsEvidenceItem(
            evidence_id=evidence_id,
            kind="file_span" if normalized_span else "file",
            path=rel_path,
            span=normalized_span,
            content_hash=f"sha256:{content_hash}",
            token_count=token_count,
        )


@dataclass(frozen=True)
class _PathReference:
    path: str
    span: str | None = None


def generate_token_economics_report(
    workspace: Path,
    *,
    include_failures: bool = False,
    since: str | None = None,
    until: str | None = None,
    ignore_session_ids: set[str] | None = None,
    ignore_tool_call_ids: set[str] | None = None,
) -> TokenEconomicsReport:
    workspace_root = _workspace_root(workspace)
    store = TokenEconomicsStore(workspace_root)
    ignore_session_ids = ignore_session_ids or set()
    ignore_tool_call_ids = ignore_tool_call_ids or set()
    all_events = store.load_events()
    filtered: list[TokenEconomicsEvent] = []
    ignored = 0
    for event in all_events:
        should_ignore = (
            event.session_id in ignore_session_ids
            or event.tool_call_id in ignore_tool_call_ids
            or (not include_failures and event.status != "success")
            or (since is not None and event.started_at < _normalize_date_filter(since, end_of_day=False))
            or (until is not None and event.started_at > _normalize_date_filter(until, end_of_day=True))
        )
        if should_ignore:
            ignored += 1
            continue
        filtered.append(event)
    events = tuple(filtered)
    return TokenEconomicsReport(
        generated_at=_timestamp(datetime.now(UTC)),
        workspace=str(workspace_root),
        include_failures=include_failures,
        ignored_event_count=ignored,
        total=_aggregate("total", events),
        by_session=tuple(
            _aggregate(session_id, tuple(group))
            for session_id, group in _group_by(events, lambda event: event.session_id).items()
        ),
        by_day=tuple(
            _aggregate(day, tuple(group))
            for day, group in _group_by(events, lambda event: event.started_at[:10]).items()
        ),
        by_tool=tuple(
            _aggregate(tool_name, tuple(group))
            for tool_name, group in _group_by(events, lambda event: event.tool_name).items()
        ),
    )


def _aggregate(name: str, events: tuple[TokenEconomicsEvent, ...]) -> TokenEconomicsAggregate:
    unique_evidence: dict[str, TokenEconomicsEvidenceItem] = {}
    for event in events:
        for item in event.evidence_items:
            unique_evidence.setdefault(item.evidence_id, item)
    total_response = sum(event.response_tokens for event in events)
    total_evidence = sum(event.evidence_footprint_tokens for event in events)
    unique_tokens = sum(item.token_count for item in unique_evidence.values())
    durations = tuple(event.elapsed_ms for event in events)
    return TokenEconomicsAggregate(
        name=name,
        event_count=len(events),
        success_count=sum(1 for event in events if event.status == "success"),
        failure_count=sum(1 for event in events if event.status != "success"),
        total_elapsed_ms=sum(event.elapsed_ms for event in events),
        avg_elapsed_ms=round((sum(durations) / len(durations)), 2) if durations else 0.0,
        p50_elapsed_ms=_percentile(durations, 0.50),
        p95_elapsed_ms=_percentile(durations, 0.95),
        max_elapsed_ms=max(durations) if durations else 0,
        total_response_tokens=total_response,
        total_evidence_footprint_tokens=total_evidence,
        unique_evidence_tokens=unique_tokens,
        duplicate_evidence_tokens=max(0, total_evidence - unique_tokens),
        evidence_token_reduction_pct=_pct_reduction(total_response, total_evidence),
        session_unique_evidence_reduction_pct=_pct_reduction(total_response, unique_tokens),
        status_counts=dict(Counter(event.status for event in events)),
        tool_counts=dict(Counter(event.tool_name for event in events)),
    )


def _group_by(events: tuple[TokenEconomicsEvent, ...], key_func) -> dict[str, list[TokenEconomicsEvent]]:
    grouped: dict[str, list[TokenEconomicsEvent]] = defaultdict(list)
    for event in events:
        grouped[key_func(event)].append(event)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _percentile(values: tuple[int, ...], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * percentile)
    return ordered[index]


def _serialize_result(result: object) -> _SerializedResult:
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")  # type: ignore[attr-defined]
    elif isinstance(result, tuple | list | dict):
        payload = result
    else:
        payload = repr(result)
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return _SerializedResult(payload=payload, text=text)


def _collect_path_references(payload: Any) -> set[_PathReference]:
    references: set[_PathReference] = set()

    def _walk(value: Any, owner_path: str | None = None) -> None:
        if isinstance(value, dict):
            local_path = _path_from_mapping(value) or owner_path
            local_span = _span_from_mapping(value, local_path)
            if local_path is not None:
                references.add(_PathReference(path=local_path, span=local_span))
            evidence_paths = value.get("evidence_paths")
            if isinstance(evidence_paths, list | tuple):
                for evidence_path in evidence_paths:
                    if isinstance(evidence_path, str):
                        references.add(_PathReference(path=evidence_path))
            for child in value.values():
                _walk(child, local_path)
        elif isinstance(value, list | tuple):
            for child in value:
                _walk(child, owner_path)

    _walk(payload)
    return references


def _path_from_mapping(value: dict[str, Any]) -> str | None:
    for key in ("repository_rel_path", "path"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _span_from_mapping(value: dict[str, Any], local_path: str | None) -> str | None:
    span = value.get("span")
    if isinstance(span, str) and span.strip():
        if local_path is not None and span.startswith(f"{local_path}:"):
            return span.removeprefix(f"{local_path}:")
        return span
    line_start = value.get("line_start")
    line_end = value.get("line_end")
    if isinstance(line_start, int):
        if isinstance(line_end, int) and line_end != line_start:
            return f"{line_start}-{line_end}"
        return str(line_start)
    return None


def _slice_text(text: str, span: str | None) -> tuple[str, str | None]:
    if span is None:
        return text, None
    parsed = _parse_span(span)
    if parsed is None:
        return text, None
    start, end = parsed
    lines = text.splitlines(keepends=True)
    if start < 1 or end < start or start > len(lines):
        return text, None
    selected = "".join(lines[start - 1 : min(end, len(lines))])
    return selected, str(start) if start == end else f"{start}-{end}"


def _parse_span(span: str) -> tuple[int, int] | None:
    normalized = span.strip()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[-1]
    if "-" in normalized:
        start_raw, end_raw = normalized.split("-", 1)
    else:
        start_raw = end_raw = normalized
    try:
        return int(start_raw), int(end_raw)
    except ValueError:
        return None


def _workspace_root(workspace: Path) -> Path:
    resolved = workspace.expanduser().resolve()
    if resolved.name == ".suit":
        return resolved.parent
    if (resolved / ".suit").exists():
        return resolved
    return resolved


def _detail_level(arguments: dict[str, object]) -> str | None:
    value = arguments.get("detail_level")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def _targets(arguments: dict[str, object]) -> tuple[str, ...]:
    value = arguments.get("repository_rel_paths")
    if isinstance(value, tuple | list):
        return tuple(str(item) for item in value if isinstance(item, str))
    single = arguments.get("repository_rel_path")
    if isinstance(single, str) and single.strip():
        return (single,)
    return tuple()


def _project_id(repository_root: Path) -> str:
    return f"sha256:{sha256(str(repository_root).encode('utf-8')).hexdigest()}"


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_date_filter(value: str, *, end_of_day: bool) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("date filter must not be empty")
    if len(stripped) == 10:
        suffix = "T23:59:59.999Z" if end_of_day else "T00:00:00.000Z"
        return stripped + suffix
    if stripped.endswith("Z"):
        datetime.fromisoformat(stripped[:-1] + "+00:00")
        return stripped
    parsed = datetime.fromisoformat(stripped)
    return _timestamp(parsed)


def _pct_reduction(response_tokens: int, evidence_tokens: int) -> float:
    if evidence_tokens <= 0:
        return 0.0
    return round(100.0 * (1.0 - (response_tokens / evidence_tokens)), 2)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip("/").removeprefix("./")


def _looks_external(path: str) -> bool:
    normalized = path.strip()
    return (
        not normalized
        or "://" in normalized
        or normalized.startswith("<")
        or Path(normalized).is_absolute()
        or normalized.startswith("..")
    )


def _truncate_error(value: str, max_chars: int = 400) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3] + "..."
