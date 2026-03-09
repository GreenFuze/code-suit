from __future__ import annotations

from inspect import signature
from pathlib import Path
from time import perf_counter
from typing import Callable

from suitcode.analytics.recorder import ToolCallRecorder


class RecordedCallExecutor:
    def __init__(
        self,
        recorder: ToolCallRecorder,
        *,
        repository_root_resolver: Callable[[str, dict[str, object]], Path | None],
    ) -> None:
        self._recorder = recorder
        self._repository_root_resolver = repository_root_resolver

    def execute(
        self,
        *,
        tool_name: str,
        callable_obj: Callable[..., object],
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> object:
        bound = signature(callable_obj).bind_partial(*args, **kwargs)
        arguments = dict(bound.arguments)
        repository_root = self._repository_root_resolver(tool_name, arguments)
        start = perf_counter()
        try:
            result = callable_obj(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((perf_counter() - start) * 1000)
            self._recorder.record_error(
                tool_name=tool_name,
                arguments=arguments,
                repository_root=repository_root,
                error=exc,
                duration_ms=duration_ms,
            )
            raise
        duration_ms = int((perf_counter() - start) * 1000)
        self._recorder.record_success(
            tool_name=tool_name,
            arguments=arguments,
            repository_root=repository_root,
            result=result,
            duration_ms=duration_ms,
        )
        return result
