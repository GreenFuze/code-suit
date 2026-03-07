from __future__ import annotations

from functools import wraps
from inspect import signature
from time import perf_counter
from typing import TYPE_CHECKING, Callable

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from suitcode.mcp.service import SuitMcpService


class McpToolInstrumentation:
    def __init__(self, service: SuitMcpService) -> None:
        self._service = service

    def install(self, app: FastMCP) -> Callable[[], None]:
        original_tool = app.tool
        recorder = self._service.analytics_recorder

        def _instrumented_tool(*args, **kwargs):
            tool_name = kwargs.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("instrumented MCP tools must define non-empty `name`")
            base_decorator = original_tool(*args, **kwargs)

            def _decorator(func):
                func_signature = signature(func)

                @wraps(func)
                def wrapped(*func_args, **func_kwargs):
                    start = perf_counter()
                    bound = func_signature.bind_partial(*func_args, **func_kwargs)
                    arguments = dict(bound.arguments)
                    repository_root = self._service.resolve_analytics_repository_root(arguments)
                    try:
                        result = func(*func_args, **func_kwargs)
                    except Exception as exc:  # noqa: BLE001
                        duration_ms = int((perf_counter() - start) * 1000)
                        recorder.record_error(
                            tool_name=tool_name,
                            arguments=arguments,
                            repository_root=repository_root,
                            error=exc,
                            duration_ms=duration_ms,
                        )
                        raise
                    duration_ms = int((perf_counter() - start) * 1000)
                    recorder.record_success(
                        tool_name=tool_name,
                        arguments=arguments,
                        repository_root=repository_root,
                        result=result,
                        duration_ms=duration_ms,
                    )
                    return result

                return base_decorator(wrapped)

            return _decorator

        app.tool = _instrumented_tool  # type: ignore[assignment]

        def _restore() -> None:
            app.tool = original_tool  # type: ignore[assignment]

        return _restore
