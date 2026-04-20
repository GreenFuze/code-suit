from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time
from threading import RLock

from suitcode.mcp.models import ToolTimingStageView, ToolTimingTargetView, ToolTimingView


@dataclass
class _TargetTimingData:
    elapsed_ms: int = 0
    status: str = "completed"
    stage_order: list[str] = field(default_factory=list)
    stage_elapsed_ms: dict[str, int] = field(default_factory=dict)

    def record_stage(self, name: str, elapsed_ms: int) -> None:
        if name not in self.stage_elapsed_ms:
            self.stage_order.append(name)
            self.stage_elapsed_ms[name] = 0
        self.stage_elapsed_ms[name] += elapsed_ms
        self.elapsed_ms += elapsed_ms


class RequestTimingCollector:
    _MAX_PUBLIC_STAGES = 8
    _MAX_PUBLIC_TARGETS = 5

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self._started_at = time.perf_counter()
        self._repository_reused: bool | None = None
        self._stage_order: list[str] = []
        self._stage_elapsed_ms: dict[str, int] = {}
        self._targets: dict[str, _TargetTimingData] = {}
        self._lock = RLock()

    def set_repository_reused(self, reused: bool | None) -> None:
        with self._lock:
            self._repository_reused = reused

    @contextmanager
    def stage(self, name: str):
        started_at = time.perf_counter()
        try:
            yield
        finally:
            with self._lock:
                self._record_stage(name, self._elapsed_ms(started_at))

    @contextmanager
    def target_stage(self, repository_rel_path: str, name: str):
        started_at = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = self._elapsed_ms(started_at)
            with self._lock:
                self._record_stage(name, elapsed_ms)
                self._target(repository_rel_path).record_stage(name, elapsed_ms)

    def mark_target_status(self, repository_rel_path: str, status: str) -> None:
        with self._lock:
            self._target(repository_rel_path).status = status

    def snapshot(self) -> ToolTimingView:
        with self._lock:
            repository_reused = self._repository_reused
            stages = tuple(
                ToolTimingStageView(name=name, elapsed_ms=self._stage_elapsed_ms[name])
                for name in self._stage_order[: self._MAX_PUBLIC_STAGES]
            )
            public_targets = sorted(
                (
                    (repository_rel_path, target)
                    for repository_rel_path, target in self._targets.items()
                    if target.stage_order
                ),
                key=lambda item: (-item[1].elapsed_ms, item[0]),
            )
            slow_targets = tuple(
                ToolTimingTargetView(
                    repository_rel_path=repository_rel_path,
                    elapsed_ms=target.elapsed_ms,
                    status=target.status,
                    dominant_stage=self._dominant_stage_name(target),
                )
                for repository_rel_path, target in public_targets[: self._MAX_PUBLIC_TARGETS]
            )
            truncated_stage_count = max(0, len(self._stage_order) - len(stages))
            truncated_target_count = max(0, len(public_targets) - len(slow_targets))
        return ToolTimingView(
            elapsed_ms=self._elapsed_ms(self._started_at),
            repository_reused=repository_reused,
            stages=stages,
            slow_targets=slow_targets,
            truncated_stage_count=truncated_stage_count,
            truncated_target_count=truncated_target_count,
        )

    def _record_stage(self, name: str, elapsed_ms: int) -> None:
        if name not in self._stage_elapsed_ms:
            self._stage_order.append(name)
            self._stage_elapsed_ms[name] = 0
        self._stage_elapsed_ms[name] += elapsed_ms

    def _target(self, repository_rel_path: str) -> _TargetTimingData:
        target = self._targets.get(repository_rel_path)
        if target is None:
            target = _TargetTimingData()
            self._targets[repository_rel_path] = target
        return target

    @staticmethod
    def _dominant_stage_name(target: _TargetTimingData) -> str | None:
        if not target.stage_order:
            return None
        ranked = max(
            enumerate(target.stage_order),
            key=lambda item: (target.stage_elapsed_ms[item[1]], -item[0]),
        )
        return ranked[1]

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))


_CURRENT_REQUEST_TIMING: ContextVar[RequestTimingCollector | None] = ContextVar(
    "suitcode_mcp_request_timing",
    default=None,
)


@contextmanager
def request_timing_collector(tool_name: str):
    collector = RequestTimingCollector(tool_name)
    token = _CURRENT_REQUEST_TIMING.set(collector)
    try:
        yield collector
    finally:
        _CURRENT_REQUEST_TIMING.reset(token)


def current_request_timing() -> RequestTimingCollector | None:
    return _CURRENT_REQUEST_TIMING.get()
