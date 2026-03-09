from __future__ import annotations

from pathlib import Path

from suitcode.analytics.call_recording import RecordedCallExecutor


class BenchmarkServiceCaller:
    def __init__(self, service: object, *, repository_root: Path) -> None:
        self._service = service
        self._repository_root = repository_root
        recorder = getattr(service, "analytics_recorder", None)
        if recorder is None:
            raise ValueError("benchmark service must expose `analytics_recorder`")
        self._recorder = recorder
        self._executor = RecordedCallExecutor(self._recorder, repository_root_resolver=self._resolve_repository_root)
        self.tool_calls = 0

    @property
    def session_id(self) -> str:
        return self._recorder.session_id

    @property
    def store(self):
        return self._recorder.store

    def call(self, method_name: str, *args, **kwargs):
        self.tool_calls += 1
        method = getattr(self._service, method_name, None)
        if method is None or not callable(method):
            raise ValueError(f"benchmark service does not expose `{method_name}`")
        return self._executor.execute(
            tool_name=method_name,
            callable_obj=method,
            args=args,
            kwargs=dict(kwargs),
        )

    def benchmark_context(self, *, run_id: str, task_id: str):
        return self._recorder.benchmark_context(run_id=run_id, task_id=task_id)

    def _resolve_repository_root(self, method_name: str, arguments: dict[str, object]) -> Path:
        if method_name == "open_workspace":
            repository_path = arguments.get("repository_path")
            if isinstance(repository_path, str) and repository_path.strip():
                return Path(repository_path).expanduser().resolve()
        resolver = getattr(self._service, "resolve_analytics_repository_root", None)
        if callable(resolver):
            resolved = resolver(arguments)
            if isinstance(resolved, Path):
                return resolved
        return self._repository_root
