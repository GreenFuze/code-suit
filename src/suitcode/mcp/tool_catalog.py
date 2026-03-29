from __future__ import annotations

from dataclasses import dataclass

from mcp.types import ToolAnnotations


@dataclass(frozen=True, slots=True)
class ToolBinding:
    name: str
    description: str
    service_method: str | None = None
    title: str | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None

    @property
    def handler_name(self) -> str:
        return self.service_method or self.name

    def to_annotations(self) -> ToolAnnotations | None:
        payload = {
            "title": self.title,
            "readOnlyHint": self.read_only_hint,
            "destructiveHint": self.destructive_hint,
            "idempotentHint": self.idempotent_hint,
            "openWorldHint": self.open_world_hint,
        }
        if all(value is None for value in payload.values()):
            return None
        return ToolAnnotations(**payload)


def _read_only(name: str, description: str, *, service_method: str | None = None, title: str | None = None) -> ToolBinding:
    return ToolBinding(
        name=name,
        description=description,
        service_method=service_method,
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _stateful(name: str, description: str, *, service_method: str | None = None, title: str | None = None) -> ToolBinding:
    return ToolBinding(
        name=name,
        description=description,
        service_method=service_method,
        title=title,
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )


def _mutating(name: str, description: str, *, service_method: str | None = None, title: str | None = None) -> ToolBinding:
    return ToolBinding(
        name=name,
        description=description,
        service_method=service_method,
        title=title,
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )


CORE_TOOL_CATALOG: tuple[ToolBinding, ...] = (
    _read_only(
        "understand_repository",
        "Start here for a supported repository when you need a deterministic summary, truth coverage, and the next high-value questions by repository path.",
        title="Core: Understand Repository",
    ),
    _read_only(
        "understand_file",
        "Start here when you need to know what owns one or more files and which related tests are closest to them by repository path. Pass `repository_rel_paths` as a list so one call can cover a whole local change set. `detail_level=compact` returns the smallest curated answer, `standard` adds limited previews, and `full` returns the current rich evidence payload. Provider-owned docs/spec files return deterministic structure instead of code-style validation guidance.",
        title="Core: Understand File",
    ),
    _read_only(
        "what_changes_if_i_edit_this",
        "Use this when one or more file changes may have blast radius. Pass `repository_rel_paths` as a list to return per-target results plus one deduplicated aggregate impact view. `detail_level=compact` returns the tightest impacted-surface answer, `standard` adds limited previews, and `full` returns the current rich evidence payload. Provider-owned docs/spec files return owned-but-empty impact when no deterministic code impact evidence exists.",
        title="Core: What Changes If I Edit This?",
    ),
    _read_only(
        "what_should_i_run",
        "Use this when you need the minimum deterministic validation set after changing one or more files by repository path. Pass `repository_rel_paths` as a list to get one deduplicated validation plan for the whole change set. Provider-owned docs/spec files return explicit exclusions when no deterministic validation surface exists.",
        title="Core: What Should I Run?",
    ),
    _read_only(
        "can_i_do_this",
        "Use this when you want a deterministic yes or no for a requested action kind on a file, plus the nearest supported alternative.",
        title="Core: Can I Do This?",
    ),
)


FULL_TOOL_CATALOG: tuple[ToolBinding, ...] = (
    _read_only("list_supported_providers", "List supported provider capabilities and ecosystems."),
    _read_only("inspect_repository_support", "Check whether a repository path is supported before opening a workspace."),
    _stateful(
        "open_workspace",
        "Stateful setup step: open or reuse a supported repository-backed workspace and return workspace_id and repository_id for later workspace-based calls. Use the *_by_path read-only tools instead when you only know repository_path and need a cold-start answer.",
    ),
    _read_only("list_open_workspaces", "List currently open workspaces held in this MCP server.", service_method="list_open_workspaces"),
    _read_only("get_workspace", "Get compact metadata for one open workspace."),
    _stateful("close_workspace", "Close one open workspace and release its repository ownership in the server.", service_method="close_workspace_result"),
    _read_only("list_workspace_repositories", "List repositories tracked in a workspace."),
    _read_only("get_repository", "Get compact repository metadata by workspace and repository ID."),
    _read_only("get_repository_by_path", "Resolve a repository in a workspace using a repository path."),
    _stateful("add_repository", "Add or reuse a supported repository inside an existing workspace."),
    _read_only(
        "repository_summary_by_path",
        "Cold-start read-only repository summary by repository path. Use this first when you know repository_path and do not yet have workspace_id or repository_id.",
    ),
    _read_only(
        "get_file_owner_by_path",
        "Cold-start read-only file owner lookup by repository path. Use this first when you know repository_path and need to identify which component, runner, package manager, or test definition owns a file.",
    ),
    _read_only(
        "get_related_tests_by_path",
        "Cold-start read-only related-test lookup by repository path. Use this first when you know repository_path and need likely related tests for a file or owner without opening a workspace.",
    ),
    _read_only(
        "get_minimum_verified_change_set_by_path",
        "Cold-start read-only answer to what should run after a change by repository path. Use this first when you know repository_path and need the smallest exact set of tests, builds, runner actions, and quality operations without opening a workspace.",
    ),
    _read_only("list_components", "Use this instead of scanning package or build files for architecture components."),
    _read_only("list_aggregators", "List architecture aggregators for a repository."),
    _read_only("list_runners", "List runnable architecture nodes for a repository."),
    _read_only("list_package_managers", "List detected package managers for a repository."),
    _read_only("list_external_packages", "List external package dependencies for a repository."),
    _read_only("list_files", "List owned files from repository intelligence instead of manual file discovery."),
    _read_only(
        "list_actions",
        "List deterministic provider-backed actions (test, runner, build) for a repository or exact target, including invocation and provenance.",
    ),
    _read_only("list_build_targets", "List deterministic build actions for this repository and their exact invocations."),
    _read_only(
        "describe_build_target",
        "Use this when you already know an exact build action ID and want invocation, ownership, and provenance context.",
    ),
    _mutating(
        "build_target",
        "Run one exact build action ID using the provider-backed deterministic invocation, with bounded timeout and structured execution output.",
    ),
    _mutating(
        "build_project",
        "Run all deterministic build actions for the repository, continue after failures, and return a structured project build summary.",
    ),
    _read_only(
        "find_symbols",
        "Use this to query repository symbols before manual code exploration. Exact full match by default, use `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    ),
    _read_only(
        "list_symbols_in_file",
        "Use this before opening a file manually. Lists symbols from one file with exact full match by default, `*` or `?` for glob matching, and `is_case_sensitive` defaults to false.",
    ),
    _read_only(
        "get_file_owner",
        "Workspace-based file owner lookup. Use this after open_workspace when you already have workspace_id and repository_id.",
    ),
    _read_only("list_files_by_owner", "Use this to inspect the file footprint of one component, runner, package manager, or test definition."),
    _read_only(
        "find_definition",
        "Find definition locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    ),
    _read_only(
        "find_references",
        "Find reference locations for a symbol or file position. This returns locations only; use `list_symbols_in_file` on the returned path to enrich the target file before opening it manually.",
    ),
    _read_only(
        "list_tests",
        "List test definitions discovered for a repository. Each result states whether discovery was authoritative tool output or heuristic fallback.",
    ),
    _read_only(
        "get_related_tests",
        "Workspace-based related-test lookup. Use this after open_workspace when you already have workspace_id and repository_id and need likely related tests for a file or owner without manual exploration.",
    ),
    _read_only("describe_test_target", "Use this when you already have one test ID and want the exact deterministic command and scope metadata to run only that target."),
    _mutating(
        "run_test_targets",
        "Run one or more exact test IDs using provider-backed deterministic commands, with bounded timeout, per-target logs, and structured failure snippets.",
    ),
    _read_only(
        "describe_runner",
        "Use this when you already have one runner ID and want invocation, ownership, related files, related tests, and provenance context in one call.",
    ),
    _mutating(
        "run_runner",
        "Run one exact runner ID using the provider-backed deterministic invocation, with bounded timeout and structured execution output.",
    ),
    _read_only("list_quality_providers", "List quality providers available for one repository.", service_method="list_quality_providers_view"),
    _mutating("lint_file", "Run the selected quality provider on one file and return structured diagnostics and entity deltas."),
    _mutating("format_file", "Run the selected formatter provider on one file and return structured change information."),
    _read_only(
        "repository_summary",
        "Workspace-based repository summary. Use this after open_workspace when you already have workspace_id and repository_id.",
    ),
    _read_only(
        "get_truth_coverage",
        "Use this to see how much of the repository's architecture, code, tests, quality, and actions are authoritative, derived, heuristic, or unavailable.",
    ),
    _read_only("describe_components", "Use this when you already know exact component IDs and want rich context for several components in one call."),
    _read_only("describe_files", "Use this when you already know exact file paths and want owner, symbol, test, and quality context before opening files manually."),
    _read_only("describe_symbol_context", "Use this when you already know an exact symbol ID and want owner, definition, reference, and related-test context."),
    _read_only("get_component_dependencies", "Use this to traverse outward from one component into its internal and external dependencies."),
    _read_only("list_component_dependency_edges", "Use this to fetch dependency edges in bulk for one component or the whole repository, with source->target and provenance."),
    _read_only("get_component_dependents", "Use this to understand the component blast radius before changing it."),
    _read_only(
        "get_analytics_summary",
        "Get aggregated MCP tool usage, latency, payload, and estimated token-savings statistics; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    _read_only(
        "get_tool_usage_analytics",
        "List per-tool analytics with call counts, error rates, latency percentiles, payload, and estimated savings; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    _read_only(
        "get_inefficient_tool_calls",
        "List detected inefficient tool usage patterns such as duplicate calls, workspace churn, pagination thrash, broad exploration, and unused high-value tools; optionally filter by repository scope, session, and global stream inclusion.",
    ),
    _read_only("get_mcp_benchmark_report", "Read the latest benchmark report generated by scripts/run_mcp_benchmark.py."),
    _read_only(
        "analyze_impact",
        "Use this to estimate change impact for one exact file, owner, or symbol without manual cross-referencing.",
    ),
    _read_only(
        "analyze_change",
        "Use this for one high-level, provenance-backed change analysis of an exact file, symbol, or owner. It tells you what owns the target, what depends on it, which references, tests, runners, and quality gates matter, and why.",
    ),
    _read_only(
        "get_minimum_verified_change_set",
        "Workspace-based answer to what should run after a change. Use this after open_workspace when you already have workspace_id and repository_id and need the smallest exact set of tests, builds, runner actions, and quality operations.",
    ),
)


TOOL_CATALOG = FULL_TOOL_CATALOG
