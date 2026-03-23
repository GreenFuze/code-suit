from __future__ import annotations

from suitcode.mcp.descriptions import TOOL_DESCRIPTIONS
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.tool_catalog import TOOL_CATALOG


def test_tool_catalog_names_are_unique() -> None:
    names = [item.name for item in TOOL_CATALOG]
    assert len(names) == len(set(names))


def test_tool_descriptions_derived_from_catalog() -> None:
    assert TOOL_DESCRIPTIONS == {item.name: item.description for item in TOOL_CATALOG}


def test_tool_catalog_handlers_exist_on_service() -> None:
    for item in TOOL_CATALOG:
        handler = getattr(SuitMcpService, item.handler_name, None)
        assert handler is not None, f"missing service method `{item.handler_name}` for tool `{item.name}`"
        assert callable(handler), f"service method `{item.handler_name}` is not callable"


def test_tool_catalog_annotations_cover_read_only_and_stateful_tools() -> None:
    by_name = {item.name: item for item in TOOL_CATALOG}

    assert by_name["repository_summary"].to_annotations().readOnlyHint is True
    assert by_name["repository_summary"].to_annotations().idempotentHint is True
    assert by_name["repository_summary"].to_annotations().destructiveHint is False

    assert by_name["repository_summary_by_path"].to_annotations().readOnlyHint is True
    assert by_name["get_minimum_verified_change_set_by_path"].to_annotations().readOnlyHint is True

    assert by_name["open_workspace"].to_annotations().readOnlyHint is False
    assert by_name["add_repository"].to_annotations().readOnlyHint is False
    assert by_name["close_workspace"].to_annotations().readOnlyHint is False

    assert by_name["run_test_targets"].to_annotations().readOnlyHint is False
    assert by_name["build_target"].to_annotations().destructiveHint is True
    assert by_name["format_file"].to_annotations().destructiveHint is True


def test_tool_catalog_descriptions_make_cold_start_vs_workspace_split_explicit() -> None:
    by_name = {item.name: item for item in TOOL_CATALOG}

    assert "cold-start" in by_name["repository_summary_by_path"].description.lower()
    assert "do not yet have workspace_id or repository_id" in by_name["repository_summary_by_path"].description
    assert "what should run after a change" in by_name["get_minimum_verified_change_set_by_path"].description.lower()

    assert "stateful setup step" in by_name["open_workspace"].description.lower()
    assert "*_by_path" in by_name["open_workspace"].description

    assert "workspace-based" in by_name["repository_summary"].description.lower()
    assert "after open_workspace" in by_name["repository_summary"].description
    assert "workspace-based" in by_name["get_file_owner"].description.lower()
    assert "workspace-based" in by_name["get_related_tests"].description.lower()
