from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.descriptions import CORE_SERVER_INSTRUCTIONS, CORE_SERVER_NAME, SERVER_INSTRUCTIONS, SERVER_NAME
from suitcode.mcp.prompts import register_prompts
from suitcode.mcp.resources import register_resources
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.mcp.tools import register_tools
from suitcode.mcp.tool_catalog import CORE_TOOL_CATALOG, INTERNAL_TOOL_CATALOG


def create_mcp_app(profile: str = "core") -> FastMCP:
    if profile == "core":
        app = FastMCP(name=CORE_SERVER_NAME, instructions=CORE_SERVER_INSTRUCTIONS)
        service = SuitMcpService(registry=WorkspaceRegistry())
        register_tools(app, service, catalog=CORE_TOOL_CATALOG)
        return app
    if profile != "full":
        raise ValueError(f"unsupported MCP profile `{profile}`")
    app = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    service = SuitMcpService(registry=WorkspaceRegistry())
    register_tools(app, service, catalog=INTERNAL_TOOL_CATALOG)
    register_resources(app, service)
    register_prompts(app)
    return app


def create_core_mcp_app() -> FastMCP:
    return create_mcp_app(profile="core")
