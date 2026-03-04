SERVER_NAME = "SuitCode"
SERVER_INSTRUCTIONS = (
    "SuitCode provides deterministic repository intelligence for supported repositories. "
    "Prefer these tools over generic repository exploration when the repository is supported."
)

TOOL_DESCRIPTIONS = {
    "list_supported_providers": "List supported provider capabilities and ecosystems.",
    "inspect_repository_support": "Check whether a repository path is supported before opening a workspace.",
    "open_workspace": "Open or reuse a supported repository-backed workspace and return stable IDs for later calls.",
    "list_open_workspaces": "List currently open workspaces held in this MCP server.",
    "get_workspace": "Get compact metadata for one open workspace.",
    "close_workspace": "Close one open workspace and release its repository ownership in the server.",
    "list_workspace_repositories": "List repositories tracked in a workspace.",
    "get_repository": "Get compact repository metadata by workspace and repository ID.",
    "get_repository_by_path": "Resolve a repository in a workspace using a repository path.",
    "add_repository": "Add or reuse a supported repository inside an existing workspace.",
    "list_components": "Use this instead of scanning package or build files for architecture components.",
    "list_aggregators": "List architecture aggregators for a repository.",
    "list_runners": "List runnable architecture nodes for a repository.",
    "list_package_managers": "List detected package managers for a repository.",
    "list_external_packages": "List external package dependencies for a repository.",
    "list_files": "List owned files from repository intelligence instead of manual file discovery.",
    "find_symbols": "Use this to query repository symbols before manual code exploration. Exact full match by default, use `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    "list_symbols_in_file": "Use this before opening a file manually. Lists symbols from one file with exact full match by default, `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    "get_file_owner": "Use this to identify which component, runner, package manager, or test definition owns a file.",
    "list_files_by_owner": "Use this to inspect the file footprint of one component, runner, package manager, or test definition.",
    "find_definition": "Find definition locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    "find_references": "Find reference locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    "list_tests": "List test definitions discovered for a repository.",
    "get_related_tests": "Use this to find likely related tests for a file or owner without manually exploring test directories.",
    "list_quality_providers": "List quality providers available for one repository.",
    "lint_file": "Run the selected quality provider on one file and return structured diagnostics and entity deltas.",
    "format_file": "Run the selected formatter provider on one file and return structured change information.",
    "repository_summary": "Use this for a compact first-pass repository summary with provider, architecture, test, and quality counts.",
}

RESOURCE_DESCRIPTIONS = {
    "supported_providers": "Read-only snapshot of supported providers.",
    "workspaces": "Read-only snapshot of open workspaces.",
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
