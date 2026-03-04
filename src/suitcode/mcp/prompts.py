from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from suitcode.mcp.descriptions import PROMPT_DESCRIPTIONS


def register_prompts(app: FastMCP) -> None:
    @app.prompt(
        name="understand_repository_with_suitcode",
        description=PROMPT_DESCRIPTIONS["understand_repository_with_suitcode"],
    )
    def understand_repository_with_suitcode() -> str:
        return (
            "Open or reuse a SuitCode workspace first. Then use list_workspace_repositories, "
            "list_components, list_tests, find_symbols, and list_files before generic repository exploration. "
            "Use built-in file exploration only after SuitCode identifies exact repositories, files, or symbols."
        )

    @app.prompt(
        name="refactor_using_suitcode_tools",
        description=PROMPT_DESCRIPTIONS["refactor_using_suitcode_tools"],
    )
    def refactor_using_suitcode_tools() -> str:
        return (
            "Open or reuse the workspace, inspect repositories, use component/test/symbol tools to locate the change, "
            "then edit precise files. Prefer SuitCode semantic tools over broad filesystem exploration."
        )

    @app.prompt(
        name="apply_quality_fix_with_suitcode",
        description=PROMPT_DESCRIPTIONS["apply_quality_fix_with_suitcode"],
    )
    def apply_quality_fix_with_suitcode() -> str:
        return (
            "List quality providers for the repository, choose one provider_id explicitly, run lint_file or format_file, "
            "and inspect diagnostics plus entity_delta before making further changes."
        )
