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
