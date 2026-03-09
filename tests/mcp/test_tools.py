from __future__ import annotations

import asyncio
import json

import pytest
from suitcode.mcp.tool_catalog import TOOL_CATALOG


async def _call_tool(app, name: str, arguments: dict):
    return await app.call_tool(name, arguments)


async def _list_tools(app):
    return await app.list_tools()


def _payload_from_result(result):
    if isinstance(result, list):
        if not result:
            raise AssertionError("tool result list is empty")
        first = result[0]
        text = getattr(first, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise AssertionError("tool result did not contain JSON text")
        return json.loads(text)
    if isinstance(result, tuple) and len(result) >= 2:
        return result[1]
    raise AssertionError(f"unsupported tool result shape: {type(result)!r}")


def test_app_registers_expected_tools(app) -> None:
    tools = asyncio.run(_list_tools(app))
    tool_names = {tool.name for tool in tools}
    expected_names = {item.name for item in TOOL_CATALOG}

    assert tool_names == expected_names

    find_symbols = next(tool for tool in tools if tool.name == "find_symbols")
    assert "Exact full match by default" in find_symbols.description
    assert "`*` or `?` for glob matching" in find_symbols.description
    assert "is_case_sensitive" in find_symbols.description

    find_definition = next(tool for tool in tools if tool.name == "find_definition")
    assert "returns locations only" in find_definition.description
    assert "list_symbols_in_file" in find_definition.description

    repository_summary = next(tool for tool in tools if tool.name == "repository_summary")
    assert "compact first-pass" in repository_summary.description

    list_actions = next(tool for tool in tools if tool.name == "list_actions")
    assert "deterministic provider-backed actions" in list_actions.description

    list_build_targets = next(tool for tool in tools if tool.name == "list_build_targets")
    assert "deterministic build actions" in list_build_targets.description

    describe_build_target = next(tool for tool in tools if tool.name == "describe_build_target")
    assert "build action ID" in describe_build_target.description

    build_target = next(tool for tool in tools if tool.name == "build_target")
    assert "bounded timeout" in build_target.description

    build_project = next(tool for tool in tools if tool.name == "build_project")
    assert "continue after failures" in build_project.description

    run_test_targets = next(tool for tool in tools if tool.name == "run_test_targets")
    assert "bounded timeout" in run_test_targets.description
    assert "failure snippets" in run_test_targets.description

    describe_runner = next(tool for tool in tools if tool.name == "describe_runner")
    assert "runner ID" in describe_runner.description
    assert "ownership" in describe_runner.description

    run_runner = next(tool for tool in tools if tool.name == "run_runner")
    assert "deterministic invocation" in run_runner.description

    analyze_impact = next(tool for tool in tools if tool.name == "analyze_impact")
    assert "change impact" in analyze_impact.description

    list_component_dependency_edges = next(tool for tool in tools if tool.name == "list_component_dependency_edges")
    assert "dependency edges in bulk" in list_component_dependency_edges.description

    get_analytics_summary = next(tool for tool in tools if tool.name == "get_analytics_summary")
    assert "estimated token-savings" in get_analytics_summary.description

    analyze_change = next(tool for tool in tools if tool.name == "analyze_change")
    assert "high-level" in analyze_change.description
    assert "quality gates" in analyze_change.description

    minimum_verified = next(tool for tool in tools if tool.name == "get_minimum_verified_change_set")
    assert "smallest exact set" in minimum_verified.description
    assert "quality operations" in minimum_verified.description

    truth_coverage = next(tool for tool in tools if tool.name == "get_truth_coverage")
    assert "authoritative" in truth_coverage.description
    assert "heuristic" in truth_coverage.description


def test_open_workspace_tool_returns_structured_result(app, npm_repo_root) -> None:
    result = asyncio.run(_call_tool(app, "open_workspace", {"repository_path": str(npm_repo_root)}))
    payload = _payload_from_result(result)

    assert payload["workspace"]["workspace_id"].startswith("workspace:")
    assert payload["initial_repository"]["repository_id"].startswith("repo:")


def test_analytics_tools_return_structured_output(app, npm_repo_root) -> None:
    opened = asyncio.run(_call_tool(app, "open_workspace", {"repository_path": str(npm_repo_root)}))
    opened_payload = _payload_from_result(opened)
    workspace_id = opened_payload["workspace"]["workspace_id"]
    repository_id = opened_payload["initial_repository"]["repository_id"]
    asyncio.run(
        _call_tool(
            app,
            "list_components",
            {
                "workspace_id": workspace_id,
                "repository_id": repository_id,
                "limit": 10,
                "offset": 0,
            },
        )
    )

    summary = _payload_from_result(asyncio.run(_call_tool(app, "get_analytics_summary", {})))
    usage = _payload_from_result(asyncio.run(_call_tool(app, "get_tool_usage_analytics", {"limit": 50, "offset": 0})))
    ineff = _payload_from_result(asyncio.run(_call_tool(app, "get_inefficient_tool_calls", {"limit": 50, "offset": 0})))

    assert summary["total_calls"] >= 2
    assert "estimated_tokens_saved" in summary
    assert isinstance(usage["items"], list)
    assert isinstance(ineff["items"], list)


def test_tool_call_fails_when_analytics_persistence_fails(app, monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise ValueError("analytics write failed")

    monkeypatch.setattr("suitcode.analytics.recorder.ToolCallRecorder.record_success", _raise)

    with pytest.raises(Exception):
        asyncio.run(_call_tool(app, "list_supported_providers", {}))
