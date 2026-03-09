from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolBinding:
    name: str
    description: str
    service_method: str | None = None

    @property
    def handler_name(self) -> str:
        return self.service_method or self.name


TOOL_CATALOG: tuple[ToolBinding, ...] = (
    ToolBinding("list_supported_providers", "List supported provider capabilities and ecosystems."),
    ToolBinding("inspect_repository_support", "Check whether a repository path is supported before opening a workspace."),
    ToolBinding("open_workspace", "Open or reuse a supported repository-backed workspace and return stable IDs for later calls."),
    ToolBinding("list_open_workspaces", "List currently open workspaces held in this MCP server.", service_method="list_open_workspaces"),
    ToolBinding("get_workspace", "Get compact metadata for one open workspace."),
    ToolBinding("close_workspace", "Close one open workspace and release its repository ownership in the server.", service_method="close_workspace_result"),
    ToolBinding("list_workspace_repositories", "List repositories tracked in a workspace."),
    ToolBinding("get_repository", "Get compact repository metadata by workspace and repository ID."),
    ToolBinding("get_repository_by_path", "Resolve a repository in a workspace using a repository path."),
    ToolBinding("add_repository", "Add or reuse a supported repository inside an existing workspace."),
    ToolBinding("list_components", "Use this instead of scanning package or build files for architecture components."),
    ToolBinding("list_aggregators", "List architecture aggregators for a repository."),
    ToolBinding("list_runners", "List runnable architecture nodes for a repository."),
    ToolBinding("list_package_managers", "List detected package managers for a repository."),
    ToolBinding("list_external_packages", "List external package dependencies for a repository."),
    ToolBinding("list_files", "List owned files from repository intelligence instead of manual file discovery."),
    ToolBinding(
        "list_actions",
        "List deterministic provider-backed actions (test, runner, build) for a repository or exact target, including invocation and provenance.",
    ),
    ToolBinding("list_build_targets", "List deterministic build actions for this repository and their exact invocations."),
    ToolBinding(
        "describe_build_target",
        "Use this when you already know an exact build action ID and want invocation, ownership, and provenance context.",
    ),
    ToolBinding(
        "build_target",
        "Run one exact build action ID using the provider-backed deterministic invocation, with bounded timeout and structured execution output.",
    ),
    ToolBinding(
        "build_project",
        "Run all deterministic build actions for the repository, continue after failures, and return a structured project build summary.",
    ),
    ToolBinding(
        "find_symbols",
        "Use this to query repository symbols before manual code exploration. Exact full match by default, use `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    ),
    ToolBinding(
        "list_symbols_in_file",
        "Use this before opening a file manually. Lists symbols from one file with exact full match by default, `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    ),
    ToolBinding("get_file_owner", "Use this to identify which component, runner, package manager, or test definition owns a file."),
    ToolBinding("list_files_by_owner", "Use this to inspect the file footprint of one component, runner, package manager, or test definition."),
    ToolBinding(
        "find_definition",
        "Find definition locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    ),
    ToolBinding(
        "find_references",
        "Find reference locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    ),
    ToolBinding(
        "list_tests",
        "List test definitions discovered for a repository. Each result states whether discovery was authoritative tool output or heuristic fallback.",
    ),
    ToolBinding(
        "get_related_tests",
        "Use this to find likely related tests for a file or owner without manually exploring test directories. Each result states whether the underlying test discovery was authoritative or heuristic.",
    ),
    ToolBinding("describe_test_target", "Use this when you already have one test ID and want the exact deterministic command and scope metadata to run only that target."),
    ToolBinding(
        "run_test_targets",
        "Run one or more exact test IDs using provider-backed deterministic commands, with bounded timeout, per-target logs, and structured failure snippets.",
    ),
    ToolBinding(
        "describe_runner",
        "Use this when you already have one runner ID and want invocation, ownership, related files, related tests, and provenance context in one call.",
    ),
    ToolBinding(
        "run_runner",
        "Run one exact runner ID using the provider-backed deterministic invocation, with bounded timeout and structured execution output.",
    ),
    ToolBinding("list_quality_providers", "List quality providers available for one repository.", service_method="list_quality_providers_view"),
    ToolBinding("lint_file", "Run the selected quality provider on one file and return structured diagnostics and entity deltas."),
    ToolBinding("format_file", "Run the selected formatter provider on one file and return structured change information."),
    ToolBinding("repository_summary", "Use this for a compact first-pass repository summary with provider, architecture, test, and quality counts."),
    ToolBinding(
        "get_truth_coverage",
        "Use this to see how much of the repository's architecture, code, tests, quality, and actions are authoritative, derived, heuristic, or unavailable.",
    ),
    ToolBinding("describe_components", "Use this when you already know exact component IDs and want rich context for several components in one call."),
    ToolBinding("describe_files", "Use this when you already know exact file paths and want owner, symbol, test, and quality context before opening files manually."),
    ToolBinding("describe_symbol_context", "Use this when you already know an exact symbol ID and want owner, definition, reference, and related-test context."),
    ToolBinding("get_component_dependencies", "Use this to traverse outward from one component into its internal and external dependencies."),
    ToolBinding("list_component_dependency_edges", "Use this to fetch dependency edges in bulk for one component or the whole repository, with source->target and provenance."),
    ToolBinding("get_component_dependents", "Use this to understand the component blast radius before changing it."),
    ToolBinding(
        "get_analytics_summary",
        "Get aggregated MCP tool usage, latency, payload, and estimated token-savings statistics; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    ToolBinding(
        "get_tool_usage_analytics",
        "List per-tool analytics with call counts, error rates, latency percentiles, payload, and estimated savings; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    ToolBinding(
        "get_inefficient_tool_calls",
        "List detected inefficient tool usage patterns such as duplicate calls, workspace churn, pagination thrash, broad exploration, and unused high-value tools; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    ToolBinding("get_mcp_benchmark_report", "Read the latest benchmark report generated by scripts/run_mcp_benchmark.py."),
    ToolBinding(
        "analyze_impact",
        "Use this to estimate change impact for one exact file, owner, or symbol without manual cross-referencing.",
    ),
    ToolBinding(
        "analyze_change",
        "Use this for one high-level, provenance-backed change analysis of an exact file, symbol, or owner. It tells you what owns the target, what depends on it, which references, tests, runners, and quality gates matter, and why.",
    ),
    ToolBinding(
        "get_minimum_verified_change_set",
        "Use this when you need the smallest exact set of tests, builds, runner actions, and quality operations required to validate a change to one file, symbol, or owner.",
    ),
)
