from __future__ import annotations

from suitcode.mcp.instrumentation import McpToolInstrumentation


class _FakeRecorder:
    def __init__(self) -> None:
        self.success_calls: list[dict] = []
        self.error_calls: list[dict] = []

    def record_success(self, **kwargs) -> None:
        self.success_calls.append(kwargs)

    def record_error(self, **kwargs) -> None:
        self.error_calls.append(kwargs)


class _FakeService:
    def __init__(self) -> None:
        self.analytics_recorder = _FakeRecorder()

    @staticmethod
    def resolve_analytics_repository_root(arguments: dict[str, object]):
        return None


class _FakeApp:
    def __init__(self) -> None:
        self.registered: dict[str, object] = {}
        self.tool = self._tool

    def _tool(self, *args, **kwargs):
        name = kwargs["name"]

        def decorator(func):
            self.registered[name] = func
            return func

        return decorator


def test_mcp_instrumentation_records_success_and_error() -> None:
    service = _FakeService()
    app = _FakeApp()
    instrumentor = McpToolInstrumentation(service)
    restore = instrumentor.install(app)  # type: ignore[arg-type]

    @app.tool(name="ok")
    def ok_tool(value: int):
        return {"value": value}

    @app.tool(name="boom")
    def boom_tool():
        raise RuntimeError("boom")

    assert app.registered["ok"](value=2) == {"value": 2}
    assert len(service.analytics_recorder.success_calls) == 1
    assert service.analytics_recorder.success_calls[0]["tool_name"] == "ok"

    try:
        app.registered["boom"]()
    except RuntimeError:
        pass
    assert len(service.analytics_recorder.error_calls) == 1
    assert service.analytics_recorder.error_calls[0]["tool_name"] == "boom"

    restore()
    assert app.tool == app._tool
