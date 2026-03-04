from __future__ import annotations

import asyncio


async def _read_resource(app, uri: str):
    return await app.read_resource(uri)


async def _list_resource_templates(app):
    return await app.list_resource_templates()


async def _list_resources(app):
    return await app.list_resources()


def test_app_registers_expected_resources(app) -> None:
    resource_uris = {resource.uriTemplate for resource in asyncio.run(_list_resource_templates(app))}
    resource_uris |= {str(resource.uri) for resource in asyncio.run(_list_resources(app))}

    assert "suitcode://supported-providers" in resource_uris
    assert "suitcode://workspaces" in resource_uris
    assert "suitcode://workspace/{workspace_id}" in resource_uris


def test_resource_returns_json_content(app, npm_repo_root) -> None:
    asyncio.run(app.call_tool("open_workspace", {"repository_path": str(npm_repo_root)}))
    contents = asyncio.run(_read_resource(app, "suitcode://workspaces"))

    assert contents[0].mime_type == "application/json"
    assert "workspace:" in contents[0].content
