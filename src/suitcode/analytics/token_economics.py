from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any
from uuid import uuid4

import tiktoken
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from suitcode.analytics.codex_session_parser import CodexSessionParser
from suitcode.analytics.codex_transcript_capture import CodexTranscriptCaptureBuilder
from suitcode.analytics.models import AnalyticsEvent, AnalyticsStatus
from suitcode.analytics.settings import AnalyticsSettings
from suitcode.analytics.storage import JsonlAnalyticsStore
from suitcode.analytics.tokenizers import OpenAiTranscriptTokenizer
from suitcode.analytics.transcript_token_estimation import TranscriptTokenEstimator
from suitcode.runtime.versioning import PROTOCOL_VERSION, build_version


TOKEN_ECONOMICS_SCHEMA_VERSION = "token_economics.v2"
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
_SLOW_REPORT_LIMIT = 10
_RUNTIME_NOT_READY_PATTERN = re.compile(
    r"runtime_not_ready:\s+tool=(?P<tool>[^ ]+)\s+server=(?P<server>[^ ]+)\s+attachment_root=(?P<root>.+?)\s+state=(?P<state>[^ ]+)\s+retry_after_seconds=(?P<retry>\d+)",
    re.IGNORECASE,
)
_ATTEMPTED_RETRIES_PATTERN = re.compile(r"attempted_retries=(?P<count>\d+)")
_DEFAULT_PUBLIC_TOOL_PROFILE = "catalog:core-read-only"
_LANGUAGE_BY_SUFFIX = {
    ".go": "go",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenizerInfo(StrictModel):
    name: str
    version: str | None = None


class TokenEconomicsRunManifest(StrictModel):
    analytics_run_id: str
    created_at: str
    project_root: str
    suitcode_build_version: str
    protocol_version: str
    coordinator_enabled: bool | None = None
    public_tool_profile: str
    tool_timeout_seconds: int | None = None
    workspace_mode: str
    model_name: str | None = None
    experiment_id: str | None = None
    experiment_label: str | None = None
    notes: str | None = None

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: str) -> str:
        if not value.endswith("Z"):
            raise ValueError("created_at must be UTC ISO-8601 with Z suffix")
        datetime.fromisoformat(value[:-1] + "+00:00")
        return value


class TokenEconomicsEvidenceItem(StrictModel):
    evidence_id: str
    kind: str
    path: str | None = None
    span: str | None = None
    content_hash: str | None = None
    token_count: int
    included_in_response: bool = False


class TokenEconomicsTimingStage(StrictModel):
    name: str
    elapsed_ms: int


class TokenEconomicsTimingTarget(StrictModel):
    repository_rel_path: str
    elapsed_ms: int
    status: str
    dominant_stage: str | None = None


class TokenEconomicsTimingView(StrictModel):
    elapsed_ms: int
    repository_reused: bool | None = None
    stages: tuple[TokenEconomicsTimingStage, ...] = Field(default_factory=tuple)
    slow_targets: tuple[TokenEconomicsTimingTarget, ...] = Field(default_factory=tuple)
    truncated_stage_count: int = 0
    truncated_target_count: int = 0


class TokenEconomicsEvent(StrictModel):
    schema_version: str = TOKEN_ECONOMICS_SCHEMA_VERSION
    project_root: str
    project_id: str
    analytics_run_id: str | None = None
    session_id: str
    task_id: str | None = None
    task_kind: str | None = None
    study_kind: str | None = None
    tool_call_id: str
    tool_name: str
    detail_level: str | None = None
    target_count: int = 0
    target_language_mix: tuple[str, ...] = Field(default_factory=tuple)
    target_file_size_bytes_total: int | None = None
    target_file_size_bytes_max: int | None = None
    repository_file_count: int | None = None
    repository_component_count: int | None = None
    repository_reused: bool | None = None
    runtime_reused: bool | None = None
    runtime_state_on_entry: str | None = None
    dominant_stage: str | None = None
    started_at: str
    finished_at: str
    elapsed_ms: int
    status: str
    error_class: str | None = None
    error_message: str | None = None
    retry_count_internal: int = 0
    runtime_not_ready_count: int = 0
    degraded_path_used: bool = False
    structural_fallback_used: bool = False
    result_truncated: bool = False
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
    authoritative_evidence_item_count: int = 0
    derived_evidence_item_count: int = 0
    heuristic_evidence_item_count: int = 0
    targets: tuple[str, ...] = Field(default_factory=tuple)
    evidence_items: tuple[TokenEconomicsEvidenceItem, ...] = Field(default_factory=tuple)
    timing: TokenEconomicsTimingView | None = None

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
            "target_count",
            "response_tokens",
            "evidence_footprint_tokens",
            "unique_session_evidence_tokens",
            "duplicate_session_evidence_tokens",
            "evidence_item_count",
            "deduped_session_evidence_item_count",
            "retry_count_internal",
            "runtime_not_ready_count",
            "authoritative_evidence_item_count",
            "derived_evidence_item_count",
            "heuristic_evidence_item_count",
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
    analytics_run_id: str | None = None
    experiment_id: str | None = None
    experiment_label: str | None = None
    event_count: int
    success_count: int
    failure_count: int
    unfinished_count: int = 0
    interrupted_count: int = 0
    degraded_count: int = 0
    fallback_count: int = 0
    retrying_call_count: int = 0
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
    suitcode_evidence_expansion_factor: float | None = None
    estimated_with_suitcode_task_tokens: int | None = None
    estimated_without_suitcode_task_tokens: int | None = None
    estimated_task_token_reduction_pct: float | None = None
    estimated_task_token_reduction_pct_response_based: float | None = None
    estimated_task_token_reduction_pct_evidence_lower_bound: float | None = None
    success_only_estimated_task_token_reduction_pct: float | None = None
    non_degraded_estimated_task_token_reduction_pct: float | None = None
    authoritative_only_estimated_task_token_reduction_pct: float | None = None
    transcript_total_tokens: int | None = None
    transcript_suitcode_tokens: int | None = None
    transcript_non_suitcode_tokens: int | None = None
    transcript_suitcode_call_count: int | None = None
    transcript_correlated_call_count: int | None = None
    transcript_coverage_partial: bool = False
    transcript_session_id: str | None = None
    transcript_artifact_path: str | None = None
    correlation_mode: str = "none"
    authoritative_evidence_rate: float = 0.0
    derived_evidence_rate: float = 0.0
    heuristic_evidence_rate: float = 0.0
    status_counts: dict[str, int]
    tool_counts: dict[str, int]


class TokenEconomicsReportFilters(StrictModel):
    include_failures: bool
    since: str | None = None
    until: str | None = None
    task_id: str | None = None
    analytics_session_id: str | None = None
    analytics_run_id: str | None = None
    experiment_id: str | None = None
    transcript_artifact_path: str | None = None
    transcript_window_padding_seconds: int | None = None
    ignored_session_ids: tuple[str, ...] = Field(default_factory=tuple)
    ignored_tool_call_ids: tuple[str, ...] = Field(default_factory=tuple)
    ignored_analytics_run_ids: tuple[str, ...] = Field(default_factory=tuple)
    ignored_transcript_artifact_paths: tuple[str, ...] = Field(default_factory=tuple)
    ignore_reason_labels: tuple[str, ...] = Field(default_factory=tuple)


class TokenEconomicsSlowCallView(StrictModel):
    tool_call_id: str
    analytics_run_id: str | None = None
    session_id: str
    task_id: str | None = None
    task_kind: str | None = None
    study_kind: str | None = None
    tool_name: str
    started_at: str
    elapsed_ms: int
    status: str
    dominant_stage: str | None = None
    targets: tuple[str, ...] = Field(default_factory=tuple)


class TokenEconomicsSlowTargetView(StrictModel):
    tool_call_id: str
    analytics_run_id: str | None = None
    session_id: str
    task_id: str | None = None
    task_kind: str | None = None
    study_kind: str | None = None
    tool_name: str
    repository_rel_path: str
    elapsed_ms: int
    status: str
    dominant_stage: str | None = None


class TokenEconomicsReport(StrictModel):
    schema_version: str = TOKEN_ECONOMICS_SCHEMA_VERSION
    report_id: str
    generated_at: str
    workspace: str
    filters: TokenEconomicsReportFilters
    ignored_event_count: int
    manifests: tuple[TokenEconomicsRunManifest, ...] = Field(default_factory=tuple)
    matched_analytics_run_ids: tuple[str, ...] = Field(default_factory=tuple)
    matched_session_ids: tuple[str, ...] = Field(default_factory=tuple)
    interpretation_notes: tuple[str, ...] = Field(default_factory=tuple)
    paper_readiness_summary: tuple[str, ...] = Field(default_factory=tuple)
    total: TokenEconomicsAggregate
    by_session: tuple[TokenEconomicsAggregate, ...]
    by_day: tuple[TokenEconomicsAggregate, ...]
    by_tool: tuple[TokenEconomicsAggregate, ...]
    by_experiment: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_analytics_run: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_task_kind: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_study_kind: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_detail_level: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_target_count_bucket: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    by_language_family: tuple[TokenEconomicsAggregate, ...] = Field(default_factory=tuple)
    slowest_calls: tuple[TokenEconomicsSlowCallView, ...] = Field(default_factory=tuple)
    slowest_targets: tuple[TokenEconomicsSlowTargetView, ...] = Field(default_factory=tuple)
    dominant_stage_counts: dict[str, int] = Field(default_factory=dict)


class TokenEconomicsArtifactSet(StrictModel):
    report_id: str
    artifact_root: str
    json_path: str
    markdown_path: str


@dataclass(frozen=True)
class _SerializedResult:
    payload: Any
    text: str


@dataclass(frozen=True)
class _TranscriptCorrelationContext:
    session_id: str
    artifact_path: str
    total_tokens: int
    suitcode_tokens: int
    non_suitcode_tokens: int
    transcript_suitcode_call_count: int
    window_start: datetime
    window_end: datetime
    metadata_confidence: str = "full"


@dataclass(frozen=True)
class _PathReference:
    path: str
    span: str | None = None


@dataclass(frozen=True)
class _IncompleteCall:
    invocation_id: str
    analytics_run_id: str | None
    session_id: str
    task_id: str | None
    task_kind: str | None
    study_kind: str | None
    tool_name: str
    started_at: str


@dataclass(frozen=True)
class _RecordedWorkload:
    targets: tuple[str, ...]
    target_language_mix: tuple[str, ...]
    target_file_size_bytes_total: int | None
    target_file_size_bytes_max: int | None
    repository_file_count: int | None
    repository_component_count: int | None
    result_truncated: bool


@dataclass(frozen=True)
class _RecordedOutcomeFlags:
    retry_count_internal: int
    runtime_not_ready_count: int
    degraded_path_used: bool
    structural_fallback_used: bool
    runtime_state_on_entry: str | None
    runtime_reused: bool | None


@dataclass(frozen=True)
class _EvidenceConfidenceCounts:
    authoritative: int
    derived: int
    heuristic: int


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


class TokenEconomicsManifestStore:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._root = self._repository_root / ".suit" / "analytics" / "token-economics"
        self._lock = RLock()

    @property
    def manifests_dir(self) -> Path:
        return self._root / "manifests"

    def ensure_manifest(self, manifest: TokenEconomicsRunManifest) -> None:
        with self._lock:
            self.manifests_dir.mkdir(parents=True, exist_ok=True)
            path = self.manifests_dir / f"{manifest.analytics_run_id}.json"
            if path.exists():
                return
            path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def load_manifests(self) -> tuple[TokenEconomicsRunManifest, ...]:
        if not self.manifests_dir.exists():
            return tuple()
        manifests: list[TokenEconomicsRunManifest] = []
        with self._lock:
            for path in sorted(self.manifests_dir.glob("*.json")):
                manifests.append(TokenEconomicsRunManifest.model_validate_json(path.read_text(encoding="utf-8")))
        return tuple(manifests)


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
                "suitcode_evidence_expansion_factor": "unique_evidence_tokens / total_response_tokens.",
                "estimated_task_token_reduction_pct_response_based": (
                    "Estimated task-level reduction that uses the transcript-observed SuitCode token cost "
                    "on the with-SuitCode side and the file-backed evidence lower bound on the without-SuitCode side."
                ),
                "estimated_task_token_reduction_pct_evidence_lower_bound": (
                    "Estimated task-level reduction that replaces transcript SuitCode segments with normalized public MCP response "
                    "tokens and compares that against the file-backed evidence lower bound."
                ),
            },
        }
        schema_file.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _RepositoryObservationCache:
    def __init__(self) -> None:
        self._repository_file_counts: dict[str, int] = {}
        self._repository_component_counts: dict[str, int] = {}

    def observe_payload(self, repository_root: Path, payload: Any) -> None:
        repository = None
        if isinstance(payload, dict):
            if isinstance(payload.get("repository"), dict):
                repository = payload["repository"]
            else:
                repository = payload
        if not isinstance(repository, dict):
            return
        root_key = str(repository_root)
        file_count = repository.get("file_count")
        component_count = repository.get("component_count")
        if isinstance(file_count, int) and file_count >= 0:
            self._repository_file_counts[root_key] = file_count
        if isinstance(component_count, int) and component_count >= 0:
            self._repository_component_counts[root_key] = component_count

    def repository_file_count(self, repository_root: Path) -> int | None:
        return self._repository_file_counts.get(str(repository_root))

    def repository_component_count(self, repository_root: Path) -> int | None:
        return self._repository_component_counts.get(str(repository_root))


class TokenEconomicsRecorder:
    def __init__(
        self,
        *,
        counter: TokenCounter | None = None,
        analytics_run_id: str | None = None,
        coordinator_enabled: bool | None = None,
        public_tool_profile: str | None = None,
        tool_timeout_seconds: int | None = None,
        workspace_mode: str | None = None,
        model_name: str | None = None,
        experiment_id: str | None = None,
        experiment_label: str | None = None,
        notes: str | None = None,
    ) -> None:
        self._counter = counter or TokenCounter()
        self._analytics_run_id = analytics_run_id or _clean_env_value(os.getenv("SUITCODE_ANALYTICS_RUN_ID")) or f"run:{uuid4().hex}"
        self._coordinator_enabled = coordinator_enabled if coordinator_enabled is not None else _env_bool("SUITCODE_COORDINATOR_ENABLED", default=True)
        self._public_tool_profile = public_tool_profile or os.getenv("SUITCODE_PUBLIC_TOOL_PROFILE") or _DEFAULT_PUBLIC_TOOL_PROFILE
        self._tool_timeout_seconds = tool_timeout_seconds if tool_timeout_seconds is not None else _env_positive_int("SUITCODE_TOOL_TIMEOUT_SECONDS")
        self._workspace_mode = (workspace_mode or os.getenv("SUITCODE_WORKSPACE_MODE") or "unknown").strip() or "unknown"
        self._model_name = model_name or _clean_env_value(os.getenv("SUITCODE_MODEL_NAME"))
        self._experiment_id = experiment_id or _clean_env_value(os.getenv("SUITCODE_ANALYTICS_EXPERIMENT_ID"))
        self._experiment_label = experiment_label or _clean_env_value(os.getenv("SUITCODE_ANALYTICS_EXPERIMENT_LABEL"))
        self._notes = notes or _clean_env_value(os.getenv("SUITCODE_ANALYTICS_NOTES"))
        self._observations = _RepositoryObservationCache()

    @property
    def analytics_run_id(self) -> str:
        return self._analytics_run_id

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
        task_kind: str | None = None,
        study_kind: str | None = None,
    ) -> TokenEconomicsEvent | None:
        if repository_root is None or tool_name not in TOKEN_ECONOMICS_TOOL_NAMES:
            return None
        repository_root = repository_root.expanduser().resolve()
        serialized = _serialize_result(result)
        self._observations.observe_payload(repository_root, serialized.payload)
        response_tokens = self._counter.count_text(serialized.text)
        evidence_items = self._collect_evidence_items(repository_root, serialized.payload)
        workload = self._build_workload(repository_root, arguments, serialized.payload)
        timing = _extract_timing(serialized.payload)
        outcome = _outcome_flags_from_payload(serialized.payload, timing=timing)
        evidence_counts = _count_provenance_modes(serialized.payload)
        return self._record(
            repository_root=repository_root,
            session_id=session_id,
            task_id=task_id,
            task_kind=task_kind,
            study_kind=study_kind,
            tool_name=tool_name,
            arguments=arguments,
            started_at=started_at,
            duration_ms=duration_ms,
            status="success",
            response_tokens=response_tokens,
            evidence_items=evidence_items,
            timing=timing,
            workload=workload,
            outcome=outcome,
            evidence_counts=evidence_counts,
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
        task_kind: str | None = None,
        study_kind: str | None = None,
    ) -> TokenEconomicsEvent | None:
        if repository_root is None or tool_name not in TOKEN_ECONOMICS_TOOL_NAMES:
            return None
        repository_root = repository_root.expanduser().resolve()
        workload = self._build_workload(repository_root, arguments, None)
        outcome = _outcome_flags_from_error(error)
        return self._record(
            repository_root=repository_root,
            session_id=session_id,
            task_id=task_id,
            task_kind=task_kind,
            study_kind=study_kind,
            tool_name=tool_name,
            arguments=arguments,
            started_at=started_at,
            duration_ms=duration_ms,
            status="error",
            response_tokens=0,
            evidence_items=tuple(),
            timing=None,
            workload=workload,
            outcome=outcome,
            evidence_counts=_EvidenceConfidenceCounts(authoritative=0, derived=0, heuristic=0),
            error_class=error.__class__.__name__,
            error_message=_truncate_error(str(error)),
        )

    def record_interrupted(
        self,
        *,
        repository_root: Path | None,
        session_id: str,
        task_id: str | None,
        tool_name: str,
        arguments: dict[str, object],
        started_at: float,
        duration_ms: int,
        reason: str,
        task_kind: str | None = None,
        study_kind: str | None = None,
    ) -> TokenEconomicsEvent | None:
        if repository_root is None or tool_name not in TOKEN_ECONOMICS_TOOL_NAMES:
            return None
        repository_root = repository_root.expanduser().resolve()
        workload = self._build_workload(repository_root, arguments, None)
        return self._record(
            repository_root=repository_root,
            session_id=session_id,
            task_id=task_id,
            task_kind=task_kind,
            study_kind=study_kind,
            tool_name=tool_name,
            arguments=arguments,
            started_at=started_at,
            duration_ms=duration_ms,
            status="interrupted",
            response_tokens=0,
            evidence_items=tuple(),
            timing=None,
            workload=workload,
            outcome=_RecordedOutcomeFlags(
                retry_count_internal=0,
                runtime_not_ready_count=0,
                degraded_path_used=False,
                structural_fallback_used=False,
                runtime_state_on_entry="unknown",
                runtime_reused=None,
            ),
            evidence_counts=_EvidenceConfidenceCounts(authoritative=0, derived=0, heuristic=0),
            error_class="InterruptedToolCall",
            error_message=_truncate_error(reason),
        )

    def _record(
        self,
        *,
        repository_root: Path,
        session_id: str,
        task_id: str | None,
        task_kind: str | None,
        study_kind: str | None,
        tool_name: str,
        arguments: dict[str, object],
        started_at: float,
        duration_ms: int,
        status: str,
        response_tokens: int,
        evidence_items: tuple[TokenEconomicsEvidenceItem, ...],
        timing: TokenEconomicsTimingView | None,
        workload: _RecordedWorkload,
        outcome: _RecordedOutcomeFlags,
        evidence_counts: _EvidenceConfidenceCounts,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> TokenEconomicsEvent:
        store = TokenEconomicsStore(repository_root)
        manifest_store = TokenEconomicsManifestStore(repository_root)
        manifest_store.ensure_manifest(self._manifest_for(repository_root))
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
            analytics_run_id=self._analytics_run_id,
            session_id=session_id,
            task_id=task_id,
            task_kind=task_kind,
            study_kind=study_kind,
            tool_call_id=f"toolcall:{uuid4().hex}",
            tool_name=tool_name,
            detail_level=_detail_level(arguments),
            target_count=len(workload.targets),
            target_language_mix=workload.target_language_mix,
            target_file_size_bytes_total=workload.target_file_size_bytes_total,
            target_file_size_bytes_max=workload.target_file_size_bytes_max,
            repository_file_count=workload.repository_file_count,
            repository_component_count=workload.repository_component_count,
            repository_reused=(None if timing is None else timing.repository_reused),
            runtime_reused=outcome.runtime_reused,
            runtime_state_on_entry=outcome.runtime_state_on_entry,
            dominant_stage=_dominant_call_stage(timing),
            started_at=_timestamp(started),
            finished_at=_timestamp(finished),
            elapsed_ms=duration_ms,
            status=status,
            error_class=error_class,
            error_message=error_message,
            retry_count_internal=outcome.retry_count_internal,
            runtime_not_ready_count=outcome.runtime_not_ready_count,
            degraded_path_used=outcome.degraded_path_used,
            structural_fallback_used=outcome.structural_fallback_used,
            result_truncated=workload.result_truncated,
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
            authoritative_evidence_item_count=evidence_counts.authoritative,
            derived_evidence_item_count=evidence_counts.derived,
            heuristic_evidence_item_count=evidence_counts.heuristic,
            targets=workload.targets,
            evidence_items=evidence_items,
            timing=timing,
        )
        store.append_event(event)
        return event

    def _manifest_for(self, repository_root: Path) -> TokenEconomicsRunManifest:
        return TokenEconomicsRunManifest(
            analytics_run_id=self._analytics_run_id,
            created_at=_timestamp(datetime.now(UTC)),
            project_root=str(repository_root),
            suitcode_build_version=build_version(),
            protocol_version=PROTOCOL_VERSION,
            coordinator_enabled=self._coordinator_enabled,
            public_tool_profile=self._public_tool_profile,
            tool_timeout_seconds=self._tool_timeout_seconds,
            workspace_mode=self._workspace_mode,
            model_name=self._model_name,
            experiment_id=self._experiment_id,
            experiment_label=self._experiment_label,
            notes=self._notes,
        )

    def _build_workload(
        self,
        repository_root: Path,
        arguments: dict[str, object],
        payload: Any,
    ) -> _RecordedWorkload:
        targets = _targets(arguments)
        sizes: list[int] = []
        languages: set[str] = set()
        for target in targets:
            languages.add(_language_family_for_path(target))
            candidate = repository_root / Path(*_normalize_path(target).split("/"))
            if candidate.is_file():
                try:
                    sizes.append(candidate.stat().st_size)
                except OSError:
                    continue
        repository_component_count = self._observations.repository_component_count(repository_root)
        repository_file_count = self._observations.repository_file_count(repository_root)
        if payload is not None:
            self._observations.observe_payload(repository_root, payload)
            repository_component_count = self._observations.repository_component_count(repository_root)
            repository_file_count = self._observations.repository_file_count(repository_root)
        return _RecordedWorkload(
            targets=targets,
            target_language_mix=tuple(sorted(language for language in languages if language != "unknown")),
            target_file_size_bytes_total=(sum(sizes) if sizes else None),
            target_file_size_bytes_max=(max(sizes) if sizes else None),
            repository_file_count=repository_file_count,
            repository_component_count=repository_component_count,
            result_truncated=_payload_has_incomplete_targets(payload),
        )

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
        reference: _PathReference,
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


def generate_token_economics_report(
    workspace: Path,
    *,
    include_failures: bool = False,
    since: str | None = None,
    until: str | None = None,
    ignore_session_ids: set[str] | None = None,
    ignore_tool_call_ids: set[str] | None = None,
    ignore_analytics_run_ids: set[str] | None = None,
    ignore_transcript_artifact_paths: set[str] | None = None,
    ignore_reason_labels: set[str] | None = None,
    task_id: str | None = None,
    analytics_session_id: str | None = None,
    analytics_run_id: str | None = None,
    experiment_id: str | None = None,
    codex_transcript_path: Path | None = None,
    transcript_window_padding_seconds: int = 300,
) -> TokenEconomicsReport:
    workspace_root = _workspace_root(workspace)
    store = TokenEconomicsStore(workspace_root)
    manifest_store = TokenEconomicsManifestStore(workspace_root)
    ignore_session_ids = ignore_session_ids or set()
    ignore_tool_call_ids = ignore_tool_call_ids or set()
    ignore_analytics_run_ids = ignore_analytics_run_ids or set()
    ignore_transcript_artifact_paths = {str(Path(item).expanduser().resolve()) for item in (ignore_transcript_artifact_paths or set())}
    ignore_reason_labels = ignore_reason_labels or set()
    if codex_transcript_path is not None and str(codex_transcript_path.expanduser().resolve()) in ignore_transcript_artifact_paths:
        codex_transcript_path = None
    transcript_context = _load_transcript_context(
        workspace_root=workspace_root,
        codex_transcript_path=codex_transcript_path,
        transcript_window_padding_seconds=transcript_window_padding_seconds,
    )
    manifests_by_id = {manifest.analytics_run_id: manifest for manifest in manifest_store.load_manifests()}
    correlation_mode = _correlation_mode(
        codex_transcript_path=codex_transcript_path,
        task_id=task_id,
        analytics_session_id=analytics_session_id,
    )
    all_events = store.load_events()
    filtered_events: list[TokenEconomicsEvent] = []
    ignored = 0
    for event in all_events:
        if _should_ignore_token_event(
            event,
            include_failures=include_failures,
            since=since,
            until=until,
            ignore_session_ids=ignore_session_ids,
            ignore_tool_call_ids=ignore_tool_call_ids,
            ignore_analytics_run_ids=ignore_analytics_run_ids,
            transcript_context=transcript_context,
            task_id=task_id,
            analytics_session_id=analytics_session_id,
            analytics_run_id=analytics_run_id,
            experiment_id=experiment_id,
            manifests_by_id=manifests_by_id,
        ):
            ignored += 1
            continue
        filtered_events.append(event)
    events = tuple(filtered_events)
    unfinished_calls = _load_unfinished_calls(
        workspace_root,
        since=since,
        until=until,
        ignore_session_ids=ignore_session_ids,
        ignore_analytics_run_ids=ignore_analytics_run_ids,
        transcript_context=transcript_context,
        task_id=task_id,
        analytics_session_id=analytics_session_id,
        analytics_run_id=analytics_run_id,
        experiment_id=experiment_id,
        manifests_by_id=manifests_by_id,
    )
    used_run_ids = {
        run_id
        for run_id in (
            *(event.analytics_run_id for event in events),
            *(call.analytics_run_id for call in unfinished_calls),
        )
        if run_id
    }
    manifests = tuple(manifests_by_id[run_id] for run_id in sorted(used_run_ids) if run_id in manifests_by_id)
    report_id = f"report:{uuid4().hex}"
    filters = TokenEconomicsReportFilters(
        include_failures=include_failures,
        since=since,
        until=until,
        task_id=task_id,
        analytics_session_id=analytics_session_id,
        analytics_run_id=analytics_run_id,
        experiment_id=experiment_id,
        transcript_artifact_path=(None if codex_transcript_path is None else str(codex_transcript_path.expanduser().resolve())),
        transcript_window_padding_seconds=transcript_window_padding_seconds if codex_transcript_path is not None else None,
        ignored_session_ids=tuple(sorted(ignore_session_ids)),
        ignored_tool_call_ids=tuple(sorted(ignore_tool_call_ids)),
        ignored_analytics_run_ids=tuple(sorted(ignore_analytics_run_ids)),
        ignored_transcript_artifact_paths=tuple(sorted(ignore_transcript_artifact_paths)),
        ignore_reason_labels=tuple(sorted(ignore_reason_labels)),
    )
    notes = _build_interpretation_notes(
        transcript_context=transcript_context,
        events=events,
        unfinished_calls=unfinished_calls,
        include_failures=include_failures,
    )
    total = _aggregate("total", events, unfinished_calls, transcript_context, correlation_mode, manifests_by_id)
    return TokenEconomicsReport(
        report_id=report_id,
        generated_at=_timestamp(datetime.now(UTC)),
        workspace=str(workspace_root),
        filters=filters,
        ignored_event_count=ignored,
        manifests=manifests,
        matched_analytics_run_ids=tuple(sorted(used_run_ids)),
        matched_session_ids=tuple(sorted({event.session_id for event in events} | {call.session_id for call in unfinished_calls})),
        interpretation_notes=notes,
        paper_readiness_summary=_paper_readiness_lines_from_total(total),
        total=total,
        by_session=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.session_id,
            lambda item: item.session_id,
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_day=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.started_at[:10],
            lambda item: item.started_at[:10],
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_tool=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.tool_name,
            lambda item: item.tool_name,
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_experiment=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: _experiment_key(event, manifests_by_id),
            lambda item: _experiment_key(item, manifests_by_id),
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_analytics_run=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.analytics_run_id or "unknown",
            lambda item: item.analytics_run_id or "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_task_kind=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.task_kind or "unknown",
            lambda item: item.task_kind or "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_study_kind=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.study_kind or "unknown",
            lambda item: item.study_kind or "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_detail_level=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: event.detail_level or "unspecified",
            lambda item: "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_target_count_bucket=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: _target_count_bucket(event.target_count),
            lambda item: "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        by_language_family=_aggregate_group(
            events,
            unfinished_calls,
            lambda event: _language_family_key(event.target_language_mix),
            lambda item: "unknown",
            transcript_context,
            correlation_mode,
            manifests_by_id,
        ),
        slowest_calls=_slowest_calls(events),
        slowest_targets=_slowest_targets(events),
        dominant_stage_counts=_dominant_stage_counts(events),
    )


def render_markdown_report(report: TokenEconomicsReport) -> str:
    total = report.total
    lines = [
        "# SuitCode Token Economics Lab Report",
        "",
        "## Experiment Metadata",
        "",
        f"- Report id: `{report.report_id}`",
        f"- Generated at: `{report.generated_at}`",
        f"- Workspace: `{report.workspace}`",
        f"- Correlation mode: `{total.correlation_mode}`",
        f"- Transcript coverage partial: `{total.transcript_coverage_partial}`",
        f"- Matched analytics runs: `{', '.join(report.matched_analytics_run_ids) if report.matched_analytics_run_ids else 'none'}`",
        f"- Matched sessions: `{', '.join(report.matched_session_ids) if report.matched_session_ids else 'none'}`",
        "",
        "## Metric Definitions",
        "",
        "- `suitcode_evidence_expansion_factor = unique_evidence_tokens / total_response_tokens`.",
        "- `estimated_task_token_reduction_pct_response_based` uses transcript-observed SuitCode token cost on the with-SuitCode side.",
        "- `estimated_task_token_reduction_pct_evidence_lower_bound` replaces transcript SuitCode segments with normalized MCP response tokens and compares that against the file-backed evidence lower bound.",
        "- All token-reduction numbers are estimates, not billing totals and not empirical A/B saved-token claims.",
        "",
        "## Primary Outcomes",
        "",
        _markdown_aggregate_table((total,)),
        "",
        "## Guardrails",
        "",
        f"- Unfinished calls: `{total.unfinished_count}`",
        f"- Interrupted calls: `{total.interrupted_count}`",
        f"- Degraded calls: `{total.degraded_count}`",
        f"- Fallback calls: `{total.fallback_count}`",
        f"- Retrying calls: `{total.retrying_call_count}`",
        f"- Authoritative evidence rate: `{total.authoritative_evidence_rate:.2f}%`",
        f"- Derived evidence rate: `{total.derived_evidence_rate:.2f}%`",
        f"- Heuristic evidence rate: `{total.heuristic_evidence_rate:.2f}%`",
        f"- Success-only estimated reduction: `{_format_optional_pct(total.success_only_estimated_task_token_reduction_pct)}`",
        f"- Non-degraded estimated reduction: `{_format_optional_pct(total.non_degraded_estimated_task_token_reduction_pct)}`",
        f"- Authoritative-only estimated reduction: `{_format_optional_pct(total.authoritative_only_estimated_task_token_reduction_pct)}`",
        "",
        "## Latency Breakdown",
        "",
        _markdown_slowest_calls(report.slowest_calls),
        "",
        _markdown_slowest_targets(report.slowest_targets),
        "",
        "## Workload Shape Breakdown",
        "",
        "### By Detail Level",
        "",
        _markdown_aggregate_table(report.by_detail_level),
        "",
        "### By Target Count Bucket",
        "",
        _markdown_aggregate_table(report.by_target_count_bucket),
        "",
        "### By Language Family",
        "",
        _markdown_aggregate_table(report.by_language_family),
        "",
        "## Longitudinal Tables",
        "",
        "### By Day",
        "",
        _markdown_aggregate_table(report.by_day),
        "",
        "### By Experiment",
        "",
        _markdown_aggregate_table(report.by_experiment),
        "",
        "### By Analytics Run",
        "",
        _markdown_aggregate_table(report.by_analytics_run),
        "",
        "### By Task Kind",
        "",
        _markdown_aggregate_table(report.by_task_kind),
        "",
        "### By Study Kind",
        "",
        _markdown_aggregate_table(report.by_study_kind),
        "",
        "## Paper-Readiness Summary",
        "",
        *(report.paper_readiness_summary or _paper_readiness_lines_from_total(total)),
        "",
        "## Threats To Validity",
        "",
    ]
    if report.interpretation_notes:
        lines.extend(f"- {note}" for note in report.interpretation_notes)
    else:
        lines.append("- No additional interpretation notes were recorded.")
    if report.manifests:
        lines.extend(
            [
                "",
                "## Included Run Manifests",
                "",
                "| analytics_run_id | experiment_id | experiment_label | build_version | protocol_version | tool_timeout_seconds | workspace_mode | coordinator_enabled | model_name |",
                "| --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for manifest in report.manifests:
            lines.append(
                "| "
                f"{manifest.analytics_run_id} | {manifest.experiment_id or '-'} | {manifest.experiment_label or '-'} | "
                f"{manifest.suitcode_build_version} | {manifest.protocol_version} | "
                f"{manifest.tool_timeout_seconds if manifest.tool_timeout_seconds is not None else '-'} | "
                f"{manifest.workspace_mode} | {manifest.coordinator_enabled if manifest.coordinator_enabled is not None else '-'} | "
                f"{manifest.model_name or '-'} |"
            )
    return "\n".join(lines) + "\n"


def write_token_economics_report_artifacts(
    workspace: Path,
    report: TokenEconomicsReport,
) -> TokenEconomicsArtifactSet:
    workspace_root = _workspace_root(workspace)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    report_id = report.report_id.replace(":", "_")
    artifact_root = workspace_root / ".suit" / "analytics" / "reports" / f"{timestamp}__{report_id}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    json_path = artifact_root / "report.json"
    markdown_path = artifact_root / "report.md"
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return TokenEconomicsArtifactSet(
        report_id=report.report_id,
        artifact_root=str(artifact_root),
        json_path=str(json_path),
        markdown_path=str(markdown_path),
    )


def _aggregate_group(
    events: tuple[TokenEconomicsEvent, ...],
    unfinished_calls: tuple[_IncompleteCall, ...],
    event_key,
    unfinished_key,
    transcript_context: _TranscriptCorrelationContext | None,
    correlation_mode: str,
    manifests_by_id: dict[str, TokenEconomicsRunManifest],
) -> tuple[TokenEconomicsAggregate, ...]:
    event_groups = _group_by(events, event_key)
    unfinished_groups = _group_unfinished(unfinished_calls, unfinished_key)
    keys = sorted(set(event_groups) | set(unfinished_groups))
    return tuple(
        _aggregate(
            key,
            tuple(event_groups.get(key, tuple())),
            tuple(unfinished_groups.get(key, tuple())),
            transcript_context,
            correlation_mode,
            manifests_by_id,
        )
        for key in keys
    )


def _aggregate(
    name: str,
    events: tuple[TokenEconomicsEvent, ...],
    unfinished_calls: tuple[_IncompleteCall, ...],
    transcript_context: _TranscriptCorrelationContext | None,
    correlation_mode: str,
    manifests_by_id: dict[str, TokenEconomicsRunManifest],
) -> TokenEconomicsAggregate:
    unique_evidence: dict[str, TokenEconomicsEvidenceItem] = {}
    for event in events:
        for item in event.evidence_items:
            unique_evidence.setdefault(item.evidence_id, item)
    total_response = sum(event.response_tokens for event in events)
    total_evidence = sum(event.evidence_footprint_tokens for event in events)
    unique_tokens = sum(item.token_count for item in unique_evidence.values())
    durations = tuple(event.elapsed_ms for event in events)
    transcript_total_tokens: int | None = None
    transcript_suitcode_tokens: int | None = None
    transcript_non_suitcode_tokens: int | None = None
    transcript_suitcode_call_count: int | None = None
    transcript_correlated_call_count: int | None = None
    transcript_coverage_partial: bool = False
    transcript_session_id: str | None = None
    transcript_artifact_path: str | None = None
    estimated_with_suitcode: int | None = None
    estimated_without_suitcode: int | None = None
    estimated_task_reduction_pct: float | None = None
    estimated_response_based: float | None = None
    estimated_evidence_lower_bound: float | None = None
    if transcript_context is not None:
        transcript_total_tokens = transcript_context.total_tokens
        transcript_suitcode_tokens = transcript_context.suitcode_tokens
        transcript_non_suitcode_tokens = transcript_context.non_suitcode_tokens
        transcript_suitcode_call_count = transcript_context.transcript_suitcode_call_count
        transcript_session_id = transcript_context.session_id
        transcript_artifact_path = transcript_context.artifact_path
        estimated_with_suitcode = transcript_non_suitcode_tokens + total_response
        estimated_without_suitcode = transcript_non_suitcode_tokens + unique_tokens
        estimated_evidence_lower_bound = _pct_reduction(
            estimated_with_suitcode,
            estimated_without_suitcode,
        )
        estimated_response_based = _pct_reduction(
            transcript_total_tokens,
            estimated_without_suitcode,
        )
        estimated_task_reduction_pct = estimated_evidence_lower_bound
    evidence_entity_total = sum(
        event.authoritative_evidence_item_count + event.derived_evidence_item_count + event.heuristic_evidence_item_count
        for event in events
    )
    authoritative_total = sum(event.authoritative_evidence_item_count for event in events)
    derived_total = sum(event.derived_evidence_item_count for event in events)
    heuristic_total = sum(event.heuristic_evidence_item_count for event in events)
    analytics_run_id = _single_value(event.analytics_run_id for event in events if event.analytics_run_id)
    manifest = manifests_by_id.get(analytics_run_id) if analytics_run_id is not None else None
    return TokenEconomicsAggregate(
        name=name,
        analytics_run_id=analytics_run_id,
        experiment_id=(None if manifest is None else manifest.experiment_id),
        experiment_label=(None if manifest is None else manifest.experiment_label),
        event_count=len(events),
        success_count=sum(1 for event in events if event.status == "success"),
        failure_count=sum(1 for event in events if event.status != "success"),
        unfinished_count=len(unfinished_calls),
        interrupted_count=sum(1 for event in events if event.status == "interrupted"),
        degraded_count=sum(1 for event in events if event.degraded_path_used),
        fallback_count=sum(1 for event in events if event.structural_fallback_used),
        retrying_call_count=sum(1 for event in events if event.retry_count_internal > 0 or event.runtime_not_ready_count > 0),
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
        suitcode_evidence_expansion_factor=_expansion_factor(unique_tokens, total_response),
        estimated_with_suitcode_task_tokens=estimated_with_suitcode,
        estimated_without_suitcode_task_tokens=estimated_without_suitcode,
        estimated_task_token_reduction_pct=estimated_task_reduction_pct,
        estimated_task_token_reduction_pct_response_based=estimated_response_based,
        estimated_task_token_reduction_pct_evidence_lower_bound=estimated_evidence_lower_bound,
        success_only_estimated_task_token_reduction_pct=_subset_estimated_pct(
            tuple(event for event in events if event.status == "success"),
            transcript_context,
            mode="evidence_lower_bound",
        ),
        non_degraded_estimated_task_token_reduction_pct=_subset_estimated_pct(
            tuple(event for event in events if not event.degraded_path_used),
            transcript_context,
            mode="evidence_lower_bound",
        ),
        authoritative_only_estimated_task_token_reduction_pct=_subset_estimated_pct(
            tuple(event for event in events if event.authoritative_evidence_item_count > 0),
            transcript_context,
            mode="evidence_lower_bound",
        ),
        transcript_total_tokens=transcript_total_tokens,
        transcript_suitcode_tokens=transcript_suitcode_tokens,
        transcript_non_suitcode_tokens=transcript_non_suitcode_tokens,
        transcript_suitcode_call_count=transcript_suitcode_call_count,
        transcript_correlated_call_count=(len(events) if transcript_context is not None else None),
        transcript_coverage_partial=(
            transcript_context is not None and len(events) < transcript_context.transcript_suitcode_call_count
        ),
        transcript_session_id=transcript_session_id,
        transcript_artifact_path=transcript_artifact_path,
        correlation_mode=correlation_mode,
        authoritative_evidence_rate=_pct(authoritative_total, evidence_entity_total),
        derived_evidence_rate=_pct(derived_total, evidence_entity_total),
        heuristic_evidence_rate=_pct(heuristic_total, evidence_entity_total),
        status_counts=dict(Counter(event.status for event in events)),
        tool_counts=dict(Counter(event.tool_name for event in events)),
    )


def _subset_estimated_pct(
    events: tuple[TokenEconomicsEvent, ...],
    transcript_context: _TranscriptCorrelationContext | None,
    *,
    mode: str,
) -> float | None:
    if transcript_context is None or not events:
        return None
    unique_evidence: dict[str, TokenEconomicsEvidenceItem] = {}
    for event in events:
        for item in event.evidence_items:
            unique_evidence.setdefault(item.evidence_id, item)
    unique_tokens = sum(item.token_count for item in unique_evidence.values())
    if unique_tokens <= 0:
        return None
    if mode == "response_based":
        return _pct_reduction(
            transcript_context.total_tokens,
            transcript_context.non_suitcode_tokens + unique_tokens,
        )
    return _pct_reduction(
        transcript_context.non_suitcode_tokens + sum(event.response_tokens for event in events),
        transcript_context.non_suitcode_tokens + unique_tokens,
    )


def _should_ignore_token_event(
    event: TokenEconomicsEvent,
    *,
    include_failures: bool,
    since: str | None,
    until: str | None,
    ignore_session_ids: set[str],
    ignore_tool_call_ids: set[str],
    ignore_analytics_run_ids: set[str],
    transcript_context: _TranscriptCorrelationContext | None,
    task_id: str | None,
    analytics_session_id: str | None,
    analytics_run_id: str | None,
    experiment_id: str | None,
    manifests_by_id: dict[str, TokenEconomicsRunManifest],
) -> bool:
    manifest = manifests_by_id.get(event.analytics_run_id or "")
    return (
        event.session_id in ignore_session_ids
        or event.tool_call_id in ignore_tool_call_ids
        or ((event.analytics_run_id or "") in ignore_analytics_run_ids)
        or (not include_failures and event.status != "success")
        or (since is not None and event.started_at < _normalize_date_filter(since, end_of_day=False))
        or (until is not None and event.started_at > _normalize_date_filter(until, end_of_day=True))
        or (transcript_context is not None and not _event_in_transcript_window(event.started_at, transcript_context))
        or (task_id is not None and event.task_id != task_id)
        or (analytics_session_id is not None and event.session_id != analytics_session_id)
        or (analytics_run_id is not None and event.analytics_run_id != analytics_run_id)
        or (experiment_id is not None and (manifest is None or manifest.experiment_id != experiment_id))
    )


def _load_unfinished_calls(
    workspace_root: Path,
    *,
    since: str | None,
    until: str | None,
    ignore_session_ids: set[str],
    ignore_analytics_run_ids: set[str],
    transcript_context: _TranscriptCorrelationContext | None,
    task_id: str | None,
    analytics_session_id: str | None,
    analytics_run_id: str | None,
    experiment_id: str | None,
    manifests_by_id: dict[str, TokenEconomicsRunManifest],
) -> tuple[_IncompleteCall, ...]:
    store = JsonlAnalyticsStore(AnalyticsSettings.from_env())
    events = store.load_events(repository_root=workspace_root, include_global=False)
    relevant = tuple(
        event
        for event in events
        if event.tool_name in TOKEN_ECONOMICS_TOOL_NAMES
        and event.invocation_id is not None
        and event.session_id not in ignore_session_ids
        and ((event.analytics_run_id or "") not in ignore_analytics_run_ids)
        and (since is None or event.timestamp_utc >= _normalize_date_filter(since, end_of_day=False))
        and (until is None or event.timestamp_utc <= _normalize_date_filter(until, end_of_day=True))
        and (transcript_context is None or _event_in_transcript_window(event.timestamp_utc, transcript_context))
        and (task_id is None or event.task_id == task_id)
        and (analytics_session_id is None or event.session_id == analytics_session_id)
        and (analytics_run_id is None or event.analytics_run_id == analytics_run_id)
        and (
            experiment_id is None
            or (
                event.analytics_run_id is not None
                and manifests_by_id.get(event.analytics_run_id) is not None
                and manifests_by_id[event.analytics_run_id].experiment_id == experiment_id
            )
        )
    )
    terminal_invocations = {
        event.invocation_id
        for event in relevant
        if event.status.is_terminal and event.invocation_id is not None
    }
    unfinished = [
        _IncompleteCall(
            invocation_id=event.invocation_id or event.event_id,
            analytics_run_id=event.analytics_run_id,
            session_id=event.session_id,
            task_id=event.task_id,
            task_kind=event.task_kind,
            study_kind=event.study_kind,
            tool_name=event.tool_name,
            started_at=event.timestamp_utc,
        )
        for event in relevant
        if event.status == AnalyticsStatus.STARTED and event.invocation_id not in terminal_invocations
    ]
    unfinished.sort(key=lambda item: (item.started_at, item.invocation_id))
    return tuple(unfinished)


def _group_by(events: tuple[TokenEconomicsEvent, ...], key_func) -> dict[str, tuple[TokenEconomicsEvent, ...]]:
    grouped: dict[str, list[TokenEconomicsEvent]] = defaultdict(list)
    for event in events:
        grouped[key_func(event)].append(event)
    return {key: tuple(grouped[key]) for key in sorted(grouped)}


def _group_unfinished(items: tuple[_IncompleteCall, ...], key) -> dict[str, tuple[_IncompleteCall, ...]]:
    grouped: dict[str, list[_IncompleteCall]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return {name: tuple(grouped[name]) for name in sorted(grouped)}


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


def _extract_timing(payload: Any) -> TokenEconomicsTimingView | None:
    if not isinstance(payload, dict):
        return None
    raw_timing = payload.get("timing")
    if not isinstance(raw_timing, dict):
        return None
    try:
        stages = tuple(
            TokenEconomicsTimingStage(name=str(item["name"]), elapsed_ms=int(item["elapsed_ms"]))
            for item in raw_timing.get("stages", ())
            if isinstance(item, dict) and "name" in item and "elapsed_ms" in item
        )
        slow_targets = tuple(
            TokenEconomicsTimingTarget(
                repository_rel_path=str(item["repository_rel_path"]),
                elapsed_ms=int(item["elapsed_ms"]),
                status=str(item["status"]),
                dominant_stage=(None if item.get("dominant_stage") in (None, "") else str(item.get("dominant_stage"))),
            )
            for item in raw_timing.get("slow_targets", ())
            if isinstance(item, dict)
            and "repository_rel_path" in item
            and "elapsed_ms" in item
            and "status" in item
        )
        return TokenEconomicsTimingView(
            elapsed_ms=int(raw_timing["elapsed_ms"]),
            repository_reused=(None if raw_timing.get("repository_reused") is None else bool(raw_timing.get("repository_reused"))),
            stages=stages,
            slow_targets=slow_targets,
            truncated_stage_count=int(raw_timing.get("truncated_stage_count", 0)),
            truncated_target_count=int(raw_timing.get("truncated_target_count", 0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


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


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round((100.0 * part) / whole, 2)


def _expansion_factor(unique_tokens: int, response_tokens: int) -> float | None:
    if response_tokens <= 0:
        return None
    return round(unique_tokens / response_tokens, 2)


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


def _correlation_mode(
    *,
    codex_transcript_path: Path | None,
    task_id: str | None,
    analytics_session_id: str | None,
) -> str:
    if codex_transcript_path is None:
        return "none"
    if task_id is not None:
        return "transcript_window_and_task_id"
    if analytics_session_id is not None:
        return "transcript_window_and_analytics_session_id"
    return "transcript_window"


def _load_transcript_context(
    *,
    workspace_root: Path,
    codex_transcript_path: Path | None,
    transcript_window_padding_seconds: int,
) -> _TranscriptCorrelationContext | None:
    if codex_transcript_path is None:
        return None
    if transcript_window_padding_seconds < 0:
        raise ValueError("transcript_window_padding_seconds must be >= 0")
    parser = CodexSessionParser()
    builder = CodexTranscriptCaptureBuilder()
    estimator = TranscriptTokenEstimator()
    artifact_path = codex_transcript_path.expanduser().resolve()
    session = parser.parse(artifact_path)
    capture = builder.build(artifact_path)
    session_with_capture = session.model_copy(update={"transcript_capture": capture})
    estimated_session = estimator.estimate_codex_session(session_with_capture)
    transcript_root = _workspace_root(Path(capture.repository_root)) if capture.repository_root else None
    if transcript_root is not None and transcript_root != workspace_root:
        raise ValueError(
            f"Codex transcript workspace `{transcript_root}` does not match requested workspace `{workspace_root}`"
        )
    tokenizer = OpenAiTranscriptTokenizer()
    suitcode_tokens = sum(tokenizer.count_segment(segment) for segment in capture.segments if segment.is_suitcode)
    total_tokens = estimated_session.token_breakdown.total_tokens if estimated_session.token_breakdown else 0
    padding = timedelta(seconds=transcript_window_padding_seconds)
    return _TranscriptCorrelationContext(
        session_id=estimated_session.session_id,
        artifact_path=str(artifact_path),
        total_tokens=total_tokens,
        suitcode_tokens=suitcode_tokens,
        non_suitcode_tokens=max(0, total_tokens - suitcode_tokens),
        transcript_suitcode_call_count=estimated_session.transcript_metrics.suitcode_tool_call_count,
        window_start=estimated_session.artifact.started_at - padding,
        window_end=estimated_session.artifact.last_event_at + padding,
        metadata_confidence=(
            "partial"
            if any("multiple session_meta entries were detected" in note for note in estimated_session.notes)
            else "full"
        ),
    )


def _event_in_transcript_window(timestamp_utc: str, transcript_context: _TranscriptCorrelationContext) -> bool:
    started_at = _parse_utc_timestamp(timestamp_utc)
    return transcript_context.window_start <= started_at <= transcript_context.window_end


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _slowest_calls(events: tuple[TokenEconomicsEvent, ...]) -> tuple[TokenEconomicsSlowCallView, ...]:
    ranked = sorted(events, key=lambda event: (-event.elapsed_ms, event.started_at, event.tool_call_id))[:_SLOW_REPORT_LIMIT]
    return tuple(
        TokenEconomicsSlowCallView(
            tool_call_id=event.tool_call_id,
            analytics_run_id=event.analytics_run_id,
            session_id=event.session_id,
            task_id=event.task_id,
            task_kind=event.task_kind,
            study_kind=event.study_kind,
            tool_name=event.tool_name,
            started_at=event.started_at,
            elapsed_ms=event.elapsed_ms,
            status=event.status,
            dominant_stage=_dominant_call_stage(event.timing),
            targets=event.targets,
        )
        for event in ranked
    )


def _slowest_targets(events: tuple[TokenEconomicsEvent, ...]) -> tuple[TokenEconomicsSlowTargetView, ...]:
    ranked_targets: list[TokenEconomicsSlowTargetView] = []
    for event in events:
        if event.timing is None:
            continue
        for target in event.timing.slow_targets:
            ranked_targets.append(
                TokenEconomicsSlowTargetView(
                    tool_call_id=event.tool_call_id,
                    analytics_run_id=event.analytics_run_id,
                    session_id=event.session_id,
                    task_id=event.task_id,
                    task_kind=event.task_kind,
                    study_kind=event.study_kind,
                    tool_name=event.tool_name,
                    repository_rel_path=target.repository_rel_path,
                    elapsed_ms=target.elapsed_ms,
                    status=target.status,
                    dominant_stage=target.dominant_stage,
                )
            )
    ranked_targets.sort(key=lambda target: (-target.elapsed_ms, target.repository_rel_path, target.tool_call_id))
    return tuple(ranked_targets[:_SLOW_REPORT_LIMIT])


def _dominant_stage_counts(events: tuple[TokenEconomicsEvent, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        timing = event.timing
        if timing is None:
            continue
        if timing.slow_targets:
            for target in timing.slow_targets:
                if target.dominant_stage:
                    counts[target.dominant_stage] += 1
            continue
        dominant_stage = _dominant_call_stage(timing)
        if dominant_stage is not None:
            counts[dominant_stage] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _dominant_call_stage(timing: TokenEconomicsTimingView | None) -> str | None:
    if timing is None or not timing.stages:
        return None
    ranked = max(enumerate(timing.stages), key=lambda item: (item[1].elapsed_ms, -item[0]))
    return ranked[1].name


def _payload_has_incomplete_targets(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    incomplete_targets = payload.get("incomplete_targets")
    return isinstance(incomplete_targets, list | tuple) and bool(incomplete_targets)


def _outcome_flags_from_payload(
    payload: Any,
    *,
    timing: TokenEconomicsTimingView | None,
) -> _RecordedOutcomeFlags:
    top_risks = _collect_risk_codes(payload) if isinstance(payload, dict) else set()
    return _RecordedOutcomeFlags(
        retry_count_internal=0,
        runtime_not_ready_count=0,
        degraded_path_used=False,
        structural_fallback_used=False,
        runtime_state_on_entry=None,
        runtime_reused=(True if timing is not None and timing.repository_reused else None),
    )


def _outcome_flags_from_error(error: Exception) -> _RecordedOutcomeFlags:
    message = _truncate_error(str(error))
    runtime_not_ready_count = 1 if "runtime_not_ready:" in message else 0
    attempted_match = _ATTEMPTED_RETRIES_PATTERN.search(message)
    retry_count_internal = int(attempted_match.group("count")) if attempted_match is not None else 0
    state_match = _RUNTIME_NOT_READY_PATTERN.search(message)
    state = state_match.group("state").lower() if state_match is not None else None
    runtime_state = None
    degraded = False
    if state in {"warming", "starting"}:
        runtime_state = "cold"
    elif state == "degraded":
        runtime_state = "degraded"
        degraded = True
    return _RecordedOutcomeFlags(
        retry_count_internal=retry_count_internal,
        runtime_not_ready_count=runtime_not_ready_count,
        degraded_path_used=degraded,
        structural_fallback_used=False,
        runtime_state_on_entry=runtime_state,
        runtime_reused=None,
    )


def _count_provenance_modes(payload: Any) -> _EvidenceConfidenceCounts:
    counts: Counter[str] = Counter()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            provenance = value.get("provenance")
            if isinstance(provenance, list | tuple):
                for item in provenance:
                    if isinstance(item, dict):
                        confidence = item.get("confidence_mode")
                        if isinstance(confidence, str):
                            normalized = confidence.strip().lower()
                            if normalized in {"authoritative", "derived", "heuristic"}:
                                counts[normalized] += 1
            for child in value.values():
                _walk(child)
        elif isinstance(value, list | tuple):
            for child in value:
                _walk(child)

    _walk(payload)
    return _EvidenceConfidenceCounts(
        authoritative=counts["authoritative"],
        derived=counts["derived"],
        heuristic=counts["heuristic"],
    )


def _collect_risk_codes(payload: Any) -> set[str]:
    risk_codes: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            risk_code = value.get("risk_code")
            if isinstance(risk_code, str) and risk_code.strip():
                risk_codes.add(risk_code.strip())
            for child in value.values():
                _walk(child)
        elif isinstance(value, list | tuple):
            for child in value:
                _walk(child)

    _walk(payload)
    return risk_codes


def _language_family_for_path(repository_rel_path: str) -> str:
    suffix = Path(repository_rel_path).suffix.lower()
    return _LANGUAGE_BY_SUFFIX.get(suffix, "unknown")


def _target_count_bucket(target_count: int) -> str:
    if target_count <= 0:
        return "0"
    if target_count == 1:
        return "1"
    if target_count <= 3:
        return "2-3"
    if target_count <= 5:
        return "4-5"
    return "6+"


def _language_family_key(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return "+".join(values)


def _experiment_key(item: TokenEconomicsEvent | _IncompleteCall, manifests_by_id: dict[str, TokenEconomicsRunManifest]) -> str:
    run_id = item.analytics_run_id
    if run_id is None:
        return "unknown"
    manifest = manifests_by_id.get(run_id)
    if manifest is None or manifest.experiment_id is None:
        return "unknown"
    if manifest.experiment_label:
        return f"{manifest.experiment_id}:{manifest.experiment_label}"
    return manifest.experiment_id


def _single_value(values) -> str | None:
    ordered = tuple(dict.fromkeys(values))
    if len(ordered) == 1:
        return ordered[0]
    return None


def _clean_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_positive_int(name: str) -> int | None:
    raw = _clean_env_value(os.getenv(name))
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _build_interpretation_notes(
    *,
    transcript_context: _TranscriptCorrelationContext | None,
    events: tuple[TokenEconomicsEvent, ...],
    unfinished_calls: tuple[_IncompleteCall, ...],
    include_failures: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    if transcript_context is None:
        notes.append("No Codex transcript was supplied, so task-level token estimates are unavailable.")
    if transcript_context is not None and not events:
        notes.append("Transcript correlation is present but no SuitCode terminal events matched the selected window and filters.")
    if transcript_context is not None and transcript_context.metadata_confidence != "full":
        notes.append("Transcript parsing detected multiple session metadata snapshots; correlation uses the latest snapshot and should be treated as partial.")
    if transcript_context is not None and events and len(events) < transcript_context.transcript_suitcode_call_count:
        notes.append(
            f"Transcript correlation is partial: matched {len(events)} terminal SuitCode events for {transcript_context.transcript_suitcode_call_count} SuitCode transcript tool calls after filters."
        )
    if unfinished_calls:
        notes.append(f"{len(unfinished_calls)} started calls did not record a terminal success/error event and are counted as unfinished.")
    if include_failures and any(event.status != "success" for event in events):
        notes.append("Failure events are included in this report revision; interpret token-efficiency metrics alongside failure counts.")
    elif any(event.status != "success" for event in events):
        notes.append("Failure events were excluded from aggregate token metrics by default; use --include-failures to inspect them directly.")
    if any(event.degraded_path_used or event.structural_fallback_used for event in events):
        notes.append("Some calls used degraded or fallback paths; token-efficiency numbers should be read alongside the guardrail sections.")
    return tuple(notes)


def _format_optional_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _format_optional_float(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _markdown_aggregate_table(items: tuple[TokenEconomicsAggregate, ...]) -> str:
    if not items:
        return "_No data._"
    rows = [
        "| name | calls | unfinished | failures | avg_ms | p95_ms | response_tokens | unique_evidence_tokens | response_based_reduction | evidence_lower_bound_reduction |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in items:
        rows.append(
            "| "
            f"{item.name} | {item.event_count} | {item.unfinished_count} | {item.failure_count} | {item.avg_elapsed_ms:.2f} | {item.p95_elapsed_ms} | "
            f"{item.total_response_tokens} | {item.unique_evidence_tokens} | "
            f"{_format_optional_pct(item.estimated_task_token_reduction_pct_response_based)} | "
            f"{_format_optional_pct(item.estimated_task_token_reduction_pct_evidence_lower_bound)} |"
        )
    return "\n".join(rows)


def _markdown_slowest_calls(items: tuple[TokenEconomicsSlowCallView, ...]) -> str:
    if not items:
        return "_No slow calls recorded._"
    rows = [
        "| elapsed_ms | tool | status | dominant_stage | targets |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for item in items:
        rows.append(
            f"| {item.elapsed_ms} | {item.tool_name} | {item.status} | {item.dominant_stage or '-'} | {', '.join(item.targets) if item.targets else '-'} |"
        )
    return "\n".join(rows)


def _markdown_slowest_targets(items: tuple[TokenEconomicsSlowTargetView, ...]) -> str:
    if not items:
        return "_No slow targets recorded._"
    rows = [
        "| elapsed_ms | tool | repository_rel_path | status | dominant_stage |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for item in items:
        rows.append(
            f"| {item.elapsed_ms} | {item.tool_name} | {item.repository_rel_path} | {item.status} | {item.dominant_stage or '-'} |"
        )
    return "\n".join(rows)


def _paper_readiness_lines_from_total(total: TokenEconomicsAggregate) -> tuple[str, ...]:
    supported_claim = (
        "Evidence-side compression with latency/reliability/evidence-quality guardrails is supported."
        if total.event_count > 0
        else "No paper-facing claim is supported because the selected slice contains no terminal SuitCode events."
    )
    if total.estimated_task_token_reduction_pct_response_based is not None and total.estimated_task_token_reduction_pct_response_based >= 0:
        supported_claim = "Task-level token-efficiency estimates are supported with guardrails for this slice."
    unsupported_claims: list[str] = []
    if total.estimated_task_token_reduction_pct_response_based is None:
        unsupported_claims.append("response-based task-level token reduction is not available for this slice")
    elif total.estimated_task_token_reduction_pct_response_based < 0:
        unsupported_claims.append("a broad end-to-end token-saving claim is not yet supported because the response-based estimate remains negative")
    if total.transcript_coverage_partial:
        unsupported_claims.append("full transcript-correlated claims are not supported because coverage is partial")
    blockers: list[str] = []
    if total.unfinished_count > 0:
        blockers.append("unfinished calls remain in the selected slice")
    if total.interrupted_count > 0:
        blockers.append("interrupted calls remain in the selected slice")
    if total.failure_count > 0:
        blockers.append("non-success calls remain in the selected slice")
    if total.degraded_count > 0 or total.fallback_count > 0:
        blockers.append("degraded/fallback paths are still present")
    if total.p95_elapsed_ms > 120000:
        blockers.append("semantic latency remains high at the p95 tail")
    next_work = "Accumulate more clean MGA runs and keep tightening semantic latency before drafting the paper."
    if blockers or unsupported_claims:
        next_work = "Prioritize cleaner transcript coverage, lower semantic tail latency, and more clean MGA runs before paper drafting."
    lines = [
        f"- Supported today: {supported_claim}",
        f"- Not yet supported: {'; '.join(unsupported_claims) if unsupported_claims else 'none for this slice'}",
        f"- Main blockers: {'; '.join(blockers) if blockers else 'no immediate blockers in this slice'}",
        f"- Recommended next work: {next_work}",
    ]
    return tuple(lines)
