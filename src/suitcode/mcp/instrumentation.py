from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Callable

from mcp.server.fastmcp import FastMCP
from suitcode.analytics.call_recording import RecordedCallExecutor

if TYPE_CHECKING:
    from suitcode.mcp.service import SuitMcpService


class McpToolInstrumentation:
    def __init__(self, service: SuitMcpService) -> None:
        self._service = service

    def install(self, app: FastMCP) -> Callable[[], None]:
        original_tool = app.tool
        recorder = self._service.analytics_recorder
        executor = RecordedCallExecutor(
            recorder,
            repository_root_resolver=lambda _tool_name, arguments: self._service.resolve_analytics_repository_root(
                arguments
            ),
        )
        original_tool_signature = inspect.signature(original_tool)
        supports_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in original_tool_signature.parameters.values()
        )
        supported_keyword_names = {
            name
            for name, parameter in original_tool_signature.parameters.items()
            if parameter.kind
            in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        }

        def _instrumented_tool(*args, **kwargs):
            tool_name = kwargs.get("name")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError("instrumented MCP tools must define non-empty `name`")
            if supports_var_kwargs:
                filtered_kwargs = dict(kwargs)
            else:
                filtered_kwargs = {
                    key: value
                    for key, value in kwargs.items()
                    if key in supported_keyword_names
                }
            base_decorator = original_tool(*args, **filtered_kwargs)

            def _decorator(func):
                @wraps(func)
                def wrapped(*func_args, **func_kwargs):
                    return executor.execute(
                        tool_name=tool_name,
                        callable_obj=func,
                        args=func_args,
                        kwargs=dict(func_kwargs),
                    )

                return base_decorator(wrapped)

            return _decorator

        app.tool = _instrumented_tool  # type: ignore[assignment]

        def _restore() -> None:
            app.tool = original_tool  # type: ignore[assignment]

        return _restore
