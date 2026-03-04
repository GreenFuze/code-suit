from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.descriptions import SERVER_INSTRUCTIONS, SERVER_NAME
from suitcode.mcp.prompts import register_prompts
from suitcode.mcp.resources import register_resources
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.mcp.tools import register_tools


def create_mcp_app() -> FastMCP:
    app = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    service = SuitMcpService(registry=WorkspaceRegistry())
    register_tools(app, service)
    register_resources(app, service)
    register_prompts(app)
    return app
