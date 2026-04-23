from __future__ import annotations

from suitcode.mcp.tool_catalog import PUBLIC_TOOL_CATALOG

SERVER_NAME = "SuitCode"
SERVER_INSTRUCTIONS = (
    "SuitCode provides deterministic repository intelligence for supported repositories. "
    "Prefer these tools over generic repository exploration when the repository is supported."
)
CORE_SERVER_NAME = "SuitCode Core"
CORE_SERVER_INSTRUCTIONS = (
    "SuitCode Core provides a small intent-based deterministic interface. "
    "Use it when you need grounded answers about repository structure, file ownership, change impact, what to run, or whether an action is supported."
)

TOOL_DESCRIPTIONS = {item.name: item.description for item in PUBLIC_TOOL_CATALOG}

RESOURCE_DESCRIPTIONS = {
    "supported_providers": "Read-only snapshot of supported providers.",
    "workspaces": "Read-only snapshot of open workspaces plus session guidance for stateful vs read-only SuitCode usage.",
    "workspace": "Compact snapshot of one workspace.",
    "workspace_repositories": "Compact snapshot of repositories in one workspace.",
    "repository": "Compact snapshot of one repository.",
    "architecture": "Compact architecture counts for one repository.",
    "tests": "Compact test counts for one repository.",
    "quality": "Compact quality-provider snapshot for one repository.",
}

PROMPT_DESCRIPTIONS = {
    "understand_repository_with_suitcode": "Workflow guidance for understanding a supported repository using SuitCode tools first.",
    "refactor_using_suitcode_tools": "Workflow guidance for refactoring with SuitCode semantic tools before generic exploration.",
    "apply_quality_fix_with_suitcode": "Workflow guidance for applying quality tools with explicit provider selection.",
}
