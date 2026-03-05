from __future__ import annotations

import asyncio


async def _call_tool(app, name: str, arguments: dict):
    return await app.call_tool(name, arguments)


async def _list_tools(app):
    return await app.list_tools()


def test_app_registers_expected_tools(app) -> None:
    tools = asyncio.run(_list_tools(app))
    tool_names = {tool.name for tool in tools}

    assert "open_workspace" in tool_names
    assert "list_components" in tool_names
    assert "list_actions" in tool_names
    assert "find_symbols" in tool_names
    assert "list_symbols_in_file" in tool_names
    assert "get_file_owner" in tool_names
    assert "list_files_by_owner" in tool_names
    assert "find_definition" in tool_names
    assert "find_references" in tool_names
    assert "get_related_tests" in tool_names
    assert "describe_test_target" in tool_names
    assert "run_test_targets" in tool_names
    assert "repository_summary" in tool_names
    assert "describe_components" in tool_names
    assert "describe_files" in tool_names
    assert "describe_symbol_context" in tool_names
    assert "get_component_dependencies" in tool_names
    assert "get_component_dependents" in tool_names
    assert "analyze_impact" in tool_names
    assert "analyze_change" in tool_names
    assert "lint_file" in tool_names

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

    run_test_targets = next(tool for tool in tools if tool.name == "run_test_targets")
    assert "bounded timeout" in run_test_targets.description
    assert "failure snippets" in run_test_targets.description

    analyze_impact = next(tool for tool in tools if tool.name == "analyze_impact")
    assert "change impact" in analyze_impact.description

    analyze_change = next(tool for tool in tools if tool.name == "analyze_change")
    assert "high-level" in analyze_change.description
    assert "quality gates" in analyze_change.description


def test_open_workspace_tool_returns_structured_result(app, npm_repo_root) -> None:
    result = asyncio.run(_call_tool(app, "open_workspace", {"repository_path": str(npm_repo_root)}))

    assert result[0][0].type == "text"
    assert "workspace_id" in result[0][0].text
    assert result[1]["workspace"]["workspace_id"].startswith("workspace:")
