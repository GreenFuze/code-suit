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
            "Use deterministic SuitCode flow: inspect_repository_support, open_workspace, and repository_summary first. "
            "Then prefer exact context tools (describe_components, describe_files, describe_symbol_context) and "
            "impact tools (analyze_change or analyze_impact) before broad list/find exploration. "
            "Use generic file exploration only after SuitCode narrows to exact files, symbols, tests, or actions."
        )

    @app.prompt(
        name="refactor_using_suitcode_tools",
        description=PROMPT_DESCRIPTIONS["refactor_using_suitcode_tools"],
    )
    def refactor_using_suitcode_tools() -> str:
        return (
            "Start with repository_summary, then use describe_* and analyze_change to build exact change scope. "
            "Use get_related_tests + describe_test_target and list_build_targets + describe_build_target for deterministic "
            "execution steps. Avoid repeated broad list/find pagination when deterministic context tools can answer directly."
        )

    @app.prompt(
        name="apply_quality_fix_with_suitcode",
        description=PROMPT_DESCRIPTIONS["apply_quality_fix_with_suitcode"],
    )
    def apply_quality_fix_with_suitcode() -> str:
        return (
            "List quality providers, choose provider_id explicitly, run lint_file or format_file, and inspect diagnostics "
            "plus entity_delta. After quality changes, use analyze_change and targeted test/build actions to verify impact."
        )
