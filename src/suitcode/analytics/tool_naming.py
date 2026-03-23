from __future__ import annotations


MCP_PREFIXES = ("mcp__", "functions.mcp__")
SUITCODE_PREFIXES = ("mcp__suitcode__", "functions.mcp__suitcode__", "suitcode__", "suitcode.")


def is_mcp_tool_name(tool_name: str) -> bool:
    return tool_name.startswith(MCP_PREFIXES)


def canonical_suitcode_tool_name(tool_name: str, *, server_name: str | None = None) -> str | None:
    normalized = tool_name.strip()
    for prefix in SUITCODE_PREFIXES:
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix) :].strip()
            if not suffix:
                raise ValueError(f"invalid SuitCode tool name `{tool_name}`")
            return suffix

    if server_name is not None and server_name.strip().lower() == "suitcode":
        if not normalized:
            raise ValueError("SuitCode tool name must not be empty when server_name=`suitcode`")
        if "__" in normalized:
            return normalized.rsplit("__", 1)[-1].strip() or None
        if "." in normalized:
            return normalized.rsplit(".", 1)[-1].strip() or None
        return normalized

    return None
