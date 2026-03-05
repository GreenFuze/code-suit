# SuitCode

SuitCode is a deterministic repository intelligence engine with an MCP server front-end.

It is designed to answer repository questions through real toolchains (manifest/build/LSP/test/quality) instead of broad file exploration.

## What SuitCode Can Do Today

For supported repositories, SuitCode provides:
- Architecture intelligence: components, aggregators, runners, package managers, external packages, owned files.
- Code intelligence: symbols, symbols-in-file, definitions, references.
- Test intelligence: discovered tests, related tests, exact test target execution.
- Quality intelligence: lint/format with structured diagnostics and symbol/entity deltas.
- Composed intelligence: repository summary, component/file/symbol context, impact analysis, change analysis.
- Deterministic execution surfaces: test actions, runner actions, build actions.

## Supported Providers and Roles

Current provider families:
- `python`
- `npm`

Current roles:
- `architecture`
- `code`
- `test`
- `quality`

Provider behavior today:
- Python:
  - architecture from `pyproject.toml`
  - code from `basedpyright` (LSP-backed)
  - tests from `pytest --collect-only -q` when available, with heuristic fallback
  - quality from Ruff
- npm:
  - architecture from `package.json` / workspace manifests
  - code from `typescript-language-server`
  - tests from `jest --listTests` when available, with heuristic fallback
  - quality from ESLint / Prettier

## MCP Tools by Job

### Support and workspace lifecycle
- `list_supported_providers`
  - Answers: What ecosystems/roles are supported at all?
- `inspect_repository_support`
  - Answers: Is this repository supported before opening a workspace?
- `open_workspace`
  - Answers: Open this repository and return stable workspace/repository IDs.
- `list_open_workspaces`
  - Answers: Which workspaces are currently open?
- `get_workspace`
  - Answers: What repositories are tracked in this workspace?
- `close_workspace`
  - Answers: Close a workspace and release repository ownership.

### Workspace/repository access
- `list_workspace_repositories`
  - Answers: Which repositories are in this workspace?
- `get_repository`
  - Answers: Return compact metadata for a specific repository ID.
- `get_repository_by_path`
  - Answers: Resolve a repository by path inside a workspace.
- `add_repository`
  - Answers: Add/reuse a supported repository in an existing workspace.

### Architecture intelligence
- `list_components`
  - Answers: What are the real components/targets?
- `list_aggregators`
  - Answers: What architecture-level aggregators exist?
- `list_runners`
  - Answers: What runnable targets exist?
- `list_package_managers`
  - Answers: Which package managers are detected?
- `list_external_packages`
  - Answers: What external dependencies are declared?
- `list_files`
  - Answers: Which files are semantically owned in the repository model?
- `get_component_dependencies`
  - Answers: What does this component depend on?
- `list_component_dependency_edges`
  - Answers: Show dependency edges in bulk (source component -> target, with scope/provenance).
- `get_component_dependents`
  - Answers: What depends on this component?

### Action discovery and execution
- `list_actions`
  - Answers: What deterministic test/runner/build actions exist and how are they invoked?
- `list_build_targets`
  - Answers: What deterministic build targets are available?
- `describe_build_target`
  - Answers: For this build action ID, what is the exact invocation, ownership, and provenance?
- `build_target`
  - Answers: Execute one exact build action and return structured result.
- `build_project`
  - Answers: Execute all deterministic build actions and return a summary.

### Code intelligence
- `find_symbols`
  - Answers: Where does this symbol name exist repository-wide?
- `list_symbols_in_file`
  - Answers: Which symbols exist in this specific file?
- `find_definition`
  - Answers: Where is this symbol/file-position defined?
- `find_references`
  - Answers: Where is this symbol/file-position referenced?

### Ownership/context intelligence
- `get_file_owner`
  - Answers: Which owner (component/runner/package-manager/test) owns this file?
- `list_files_by_owner`
  - Answers: Which files belong to this owner?
- `repository_summary`
  - Answers: Give me a compact first-pass repository overview.
- `describe_components`
  - Answers: For exact components, what files/deps/dependents/tests/runners matter?
- `describe_files`
  - Answers: For exact files, what owner/symbol/test/quality context matters?
- `describe_symbol_context`
  - Answers: For this symbol, what owner/defs/refs/tests context matters?

### Test intelligence and execution
- `list_tests`
  - Answers: What tests were discovered, and was discovery authoritative or heuristic?
- `get_related_tests`
  - Answers: Which tests are related to this file/owner?
- `describe_test_target`
  - Answers: What is the exact deterministic command for this test target?
- `run_test_targets`
  - Answers: Execute exact test IDs and return structured execution/failure output.

### Runner intelligence and execution
- `describe_runner`
  - Answers: What is this runner, how is it invoked, what owns it, and what tests/files relate to it?
- `run_runner`
  - Answers: Execute one exact runner ID and return structured execution output.

### Quality intelligence and operations
- `list_quality_providers`
  - Answers: Which quality providers are available for this repository?
- `lint_file`
  - Answers: Lint one file and return diagnostics, deltas, and before/after metadata.
- `format_file`
  - Answers: Format one file and return structured change metadata.

### Change impact intelligence
- `analyze_impact`
  - Answers: What likely breaks if I change this file/symbol/owner?
- `analyze_change`
  - Answers: For exact file/symbol/owner, what owns it, what depends on it, what refs/tests/runners/quality gates matter, and why?

## Deterministic Execution Surfaces

SuitCode already executes provider-backed deterministic actions:
- Tests: `run_test_targets`
- Runners: `run_runner`
- Builds: `build_target`, `build_project`

It does not expose generic shell tools.
Execution is always tied to provider-backed actions and structured results.

## Provenance and Trust Model

SuitCode outputs include explicit provenance with fields like:
- `confidence_mode`
- `source_kind`
- `source_tool`
- `evidence_summary`
- `evidence_paths`

This makes authoritative tool output and heuristic fallback explicitly distinguishable.

## Fail-Fast Behavior

SuitCode is intentionally fail-fast:
- unsupported repositories fail on open
- invalid IDs/selectors fail instead of being ignored
- contradictory/invalid query combinations fail
- malformed deterministic metadata fails instead of being guessed

## How Agents Should Use SuitCode

Recommended flow:
1. `inspect_repository_support`
2. `open_workspace`
3. `repository_summary`
4. Use exact semantic tools (`describe_*`, `analyze_*`, `find_*`, `get_*`, `run_*`, `build_*`) before manual file exploration.

## Running the MCP Server (stdio-first)

Default transport is `stdio`.

Project launchers (foreground process):
- Windows: `./run_mcp.bat`
- Unix-like: `./run_mcp.sh`

Python module entrypoint:
- `python -m suitcode.mcp.server`

Optional HTTP mode:
- `python -m suitcode.mcp.server --transport http --host 127.0.0.1 --port 8000`

## MCP Resources

- `suitcode://supported-providers`
- `suitcode://workspaces`
- `suitcode://workspace/{workspace_id}`
- `suitcode://workspace/{workspace_id}/repositories`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/architecture`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/tests`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/quality`

## MCP Prompts

- `understand_repository_with_suitcode`
- `refactor_using_suitcode_tools`
- `apply_quality_fix_with_suitcode`

## Current Limits and Non-goals

Current state:
- primary ecosystems: Python and npm
- in-memory workspace/runtime state
- provider-backed deterministic intelligence surfaces

Not a current goal:
- generic indexer-first architecture
- graph DB product direction
- vector-search-first identity
- generic shell execution MCP tools
