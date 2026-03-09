# SuitCode

SuitCode is a deterministic repository intelligence engine with an MCP server front-end.

It is designed to answer repository questions through real toolchains (manifest/build/LSP/test/quality) instead of broad file exploration.

## What SuitCode Can Do Today

For supported repositories, SuitCode provides:
- Architecture intelligence: components, aggregators, runners, package managers, external packages, owned files.
- Code intelligence: symbols, symbols-in-file, definitions, references.
- Test intelligence: discovered tests, related tests, exact test target execution.
- Quality intelligence: lint/format with structured diagnostics and symbol/entity deltas.
- Composed intelligence: repository summary, component/file/symbol context, impact analysis, change analysis, minimum verified change set.
- Trust intelligence: repository-wide and change-local truth coverage across architecture, code, tests, quality, and actions.
- Deterministic execution surfaces: test actions, runner actions, build actions.
- Intelligence observability: MCP tool usage analytics, native Codex session usage analytics, transcript-estimated token accounting, estimated token-savings analytics, inefficiency detection.
- Codex-native evaluation: harness-driven `codex exec` task runs with structured scoring, deterministic baseline comparison, and stored evaluation reports.

## High-Value Questions SuitCode Answers

- What are the real components/targets and their dependencies?
  - Use `list_components`, `get_component_dependencies`, `list_component_dependency_edges`, `get_component_dependents`.
- What tests cover this component/file and how do I run only those tests?
  - Use `get_related_tests`, `describe_test_target`, `run_test_targets`.
- What breaks if I change this file/symbol/owner?
  - Use `analyze_impact` and `analyze_change`.
- What is the minimum exact validation set for this change?
  - Use `get_minimum_verified_change_set`.
- How trustworthy is SuitCode's understanding of this repository or change?
  - Use `get_truth_coverage` and inspect the `truth_coverage` attached to `repository_summary` and `analyze_change`.

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
  - Answers: Give me a compact first-pass repository overview, including trust coverage for architecture/code/tests/quality/actions.
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
  - Answers: For exact file/symbol/owner, what owns it, what depends on it, what refs/tests/runners/quality gates matter, why, and how strong the returned evidence is.
- `get_minimum_verified_change_set`
  - Answers: What is the smallest exact set of tests, build targets, runner actions, and quality operations I should validate for this change?
- `get_truth_coverage`
  - Answers: How much of this repository's architecture, code, tests, quality, and actions are authoritative, derived, heuristic, or unavailable?

### Analytics intelligence
- `get_analytics_summary`
  - Answers: How much is SuitCode being used, how often does it fail, and what is the estimated token savings?
  - Supports: optional repository scope, `session_id`, and `include_global`.
- `get_tool_usage_analytics`
  - Answers: Which tools are used most, with what latency/error profile and estimated savings impact?
  - Supports: optional repository scope, `session_id`, and `include_global`.
- `get_inefficient_tool_calls`
  - Answers: Are there duplicate calls, workspace churn, pagination thrash, broad exploration patterns, or unused high-value tools?
  - Supports: optional repository scope, `session_id`, and `include_global`.
- `get_mcp_benchmark_report`
  - Answers: What is the latest benchmark report for SuitCode MCP performance, including trust-coverage summary when available?

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

SuitCode also exposes truth coverage:
- repository-wide via `get_truth_coverage`
- additive on `repository_summary`
- additive on `analyze_change`
- additive on benchmark reports when the benchmark run is tied to a resolved repository

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
4. `get_truth_coverage` when you need to judge whether SuitCode is operating at full trust or partial visibility
5. Prefer exact context and impact tools: `describe_components`, `describe_files`, `describe_symbol_context`, `analyze_change`, `analyze_impact`, `get_minimum_verified_change_set`
6. Use broad exploration tools (`list_*`, `find_*`) only when exact context is still missing
7. Use deterministic execution tools (`describe_test_target`, `run_test_targets`, `describe_build_target`, `build_target`, `build_project`) instead of guessing commands

## Running the MCP Server (stdio-first)

Default transport is `stdio`.

Project launchers (foreground process):
- Windows: `./run_mcp.bat`
- Unix-like: `./run_mcp.sh`

Python module entrypoint:
- `python -m suitcode.mcp.server`

Optional HTTP mode:
- `python -m suitcode.mcp.server --transport http --host 127.0.0.1 --port 8000`

Local analytics scripts:
- `python scripts/analyze_analytics.py`
- `python scripts/analyze_codex_usage.py`
- `python scripts/run_mcp_benchmark.py`
- `python scripts/run_codex_eval.py`
- `python scripts/analyze_codex_eval.py`
- `python scripts/run_codex_comparison.py`
- `python scripts/analyze_codex_comparison.py`

Analytics script options:
- `python scripts/analyze_analytics.py --repository-root "<repo>"`
- `python scripts/analyze_analytics.py --repository-root "<repo>" --session-id "<session_id>"`
- `python scripts/analyze_analytics.py --repository-root "<repo>" --no-include-global`
- `python scripts/analyze_analytics.py --json`

Native Codex usage script options:
- `python scripts/analyze_codex_usage.py --repository-root "<repo>"`
- `python scripts/analyze_codex_usage.py --repository-root "<repo>" --include-correlation`
- `python scripts/analyze_codex_usage.py --repository-root "<repo>" --include-tokens`
- `python scripts/analyze_codex_usage.py --repository-root "<repo>" --include-tokens --show-segments --segment-limit 20`
- `python scripts/analyze_codex_usage.py --json`

Codex evaluation script options:
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_smoke.json`
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_readonly.json`
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_execution.json`
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_project_readonly.json --task-id <task_id>`
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_native.json --task-id <task_id>`
- `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_smoke.json --timeout-seconds 180`
- `python scripts/analyze_codex_eval.py --latest`
- `python scripts/analyze_codex_eval.py --report-id <report_id>`
- `python scripts/run_codex_comparison.py --skip-stress`
- `python scripts/run_codex_comparison.py`
- `python scripts/analyze_codex_comparison.py --latest`
- `python scripts/analyze_codex_comparison.py --report-id <report_id>`

Benchmark script options:
- `python scripts/run_mcp_benchmark.py`
- `python scripts/run_mcp_benchmark.py --tasks-file benchmarks/tasks/sample_tasks.json`
- `python scripts/run_mcp_benchmark.py --fail-on-task-error`

Token-accounting note:
- `scripts/analyze_codex_usage.py --include-tokens` reports `transcript_estimated` token metrics from visible Codex rollout content.
- These are evaluation metrics for relative comparison, not billing-accurate vendor token totals.

Codex smoke-eval note:
- `benchmarks/codex/tasks/suitcode_smoke.json` is the fast harness sanity check.
- It targets both supported ecosystems through truth-coverage smoke tasks:
  - `tests/test_repos/python`
  - `tests/test_repos/npm`
- Current reports include per-required-tool traces so timeout or tool-call failures are visible without opening rollout JSONL manually.

Codex read-only evaluation note:
- `benchmarks/codex/tasks/suitcode_readonly.json` is the stable read-only acceptance suite.
- It targets both supported ecosystems through the fixture repositories:
  - `tests/test_repos/python`
  - `tests/test_repos/npm`
- It covers:
  - `orientation`
  - `change_analysis`
  - `minimum_verified_change_set`
  - `truth_coverage`

Codex live-project stress note:
- `benchmarks/codex/tasks/suitcode_project_readonly.json` keeps the live SuitCode repository as the Python target.
- This suite is useful for stress/performance tracking, but it is not the stability gate for Codex evaluation.

Codex comparison note:
- `scripts/run_codex_comparison.py` builds the shareable Codex report bundle:
  - stable read-only A/B: SuitCode enabled vs SuitCode disabled
  - stable execution: SuitCode-only
  - optional live-project stress section
- If Codex itself is blocked by vendor quota, the comparison now fails fast instead of generating a misleading report that treats quota exhaustion as product failure.

Benchmark task workflows currently supported:
- `orientation`
- `change_impact`
- `test_execute`
- `build_execute`

The default sample benchmark covers both the current Python repository and the npm fixture repository under `tests/test_repos/npm`.

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
  - Guides the agent to start with `inspect_repository_support`, `open_workspace`, and `repository_summary`, then move to exact context and impact tools before broad exploration.
- `refactor_using_suitcode_tools`
  - Guides the agent to use `describe_*`, `analyze_change`, and deterministic test/build descriptions before editing or exploring broadly.
- `apply_quality_fix_with_suitcode`
  - Guides the agent to run quality tools first, inspect `entity_delta`, then verify impact with `analyze_change` and deterministic test/build actions.

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

