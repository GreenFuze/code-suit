from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.instrumentation import McpToolInstrumentation
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.tool_catalog import PUBLIC_TOOL_CATALOG, ToolBinding


def register_tools(app: FastMCP, service: SuitMcpService, *, catalog: tuple[ToolBinding, ...] = PUBLIC_TOOL_CATALOG) -> None:
    restore_tool = McpToolInstrumentation(service).install(app)
    try:
        for binding in catalog:
            handler = getattr(service, binding.handler_name, None)
            if handler is None or not callable(handler):
                raise ValueError(
                    f"tool `{binding.name}` references missing callable service method `{binding.handler_name}`"
                )
            app.tool(
                name=binding.name,
                description=binding.description,
                annotations=binding.to_annotations(),
                structured_output=True,
            )(handler)
    finally:
        restore_tool()
