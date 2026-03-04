from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.descriptions import RESOURCE_DESCRIPTIONS
from suitcode.mcp.service import SuitMcpService


def _json_content(model) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True)


def register_resources(app: FastMCP, service: SuitMcpService) -> None:
    @app.resource(
        "suitcode://supported-providers",
        name="supported_providers_resource",
        description=RESOURCE_DESCRIPTIONS["supported_providers"],
        mime_type="application/json",
    )
    def supported_providers_resource() -> str:
        return _json_content(service.list_supported_providers(limit=200, offset=0))

    @app.resource(
        "suitcode://workspaces",
        name="workspaces_resource",
        description=RESOURCE_DESCRIPTIONS["workspaces"],
        mime_type="application/json",
    )
    def workspaces_resource() -> str:
        return _json_content(service.list_workspaces(limit=200, offset=0))

    @app.resource(
        "suitcode://workspace/{workspace_id}",
        name="workspace_resource",
        description=RESOURCE_DESCRIPTIONS["workspace"],
        mime_type="application/json",
    )
    def workspace_resource(workspace_id: str) -> str:
        return _json_content(service.workspace_snapshot(workspace_id))

    @app.resource(
        "suitcode://workspace/{workspace_id}/repositories",
        name="workspace_repositories_resource",
        description=RESOURCE_DESCRIPTIONS["workspace_repositories"],
        mime_type="application/json",
    )
    def workspace_repositories_resource(workspace_id: str) -> str:
        return _json_content(service.list_workspace_repositories(workspace_id, limit=200, offset=0))

    @app.resource(
        "suitcode://workspace/{workspace_id}/repository/{repository_id}",
        name="repository_resource",
        description=RESOURCE_DESCRIPTIONS["repository"],
        mime_type="application/json",
    )
    def repository_resource(workspace_id: str, repository_id: str) -> str:
        return _json_content(service.repository_snapshot(workspace_id, repository_id))

    @app.resource(
        "suitcode://workspace/{workspace_id}/repository/{repository_id}/architecture",
        name="architecture_resource",
        description=RESOURCE_DESCRIPTIONS["architecture"],
        mime_type="application/json",
    )
    def architecture_resource(workspace_id: str, repository_id: str) -> str:
        return _json_content(service.architecture_snapshot(workspace_id, repository_id))

    @app.resource(
        "suitcode://workspace/{workspace_id}/repository/{repository_id}/tests",
        name="tests_resource",
        description=RESOURCE_DESCRIPTIONS["tests"],
        mime_type="application/json",
    )
    def tests_resource(workspace_id: str, repository_id: str) -> str:
        return _json_content(service.tests_snapshot(workspace_id, repository_id))

    @app.resource(
        "suitcode://workspace/{workspace_id}/repository/{repository_id}/quality",
        name="quality_resource",
        description=RESOURCE_DESCRIPTIONS["quality"],
        mime_type="application/json",
    )
    def quality_resource(workspace_id: str, repository_id: str) -> str:
        return _json_content(service.quality_snapshot(workspace_id, repository_id))
