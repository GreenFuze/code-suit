# SuitCode

SuitCode is a repository intelligence engine with an MCP server front-end.

It gives agents deterministic repository understanding for supported projects so they can use semantic tools instead of broad filesystem exploration.

Current supported provider families:
- `python`
- `npm`

Current intelligence roles:
- architecture
- code
- test
- quality

Design direction:
- providers are the source of truth
- the MCP exposes compact semantic tools over those providers
- SuitCode keeps shared typed result objects across providers
- SuitCode does not currently rely on a persisted graph/database for normal operation

## What SuitCode Knows

For a supported repository, SuitCode can expose:
- components
- aggregators
- runners
- package managers
- external packages
- owned files
- symbols
- definitions and references
- discovered tests and related tests
- quality providers, linting, and formatting
- repository/component/file/symbol context
- dependency and impact summaries

## Supported Repositories

### Python
A repository is currently considered Python-supported when it has a valid root `pyproject.toml` that identifies a Python project.

Python provider behavior:
- architecture: `pyproject.toml` driven
- code: `basedpyright` LSP-backed
- test:
  - authoritative pytest discovery via `pytest --collect-only -q` when available
  - heuristic unittest fallback
- quality: `ruff check` and `ruff format`

### npm
A repository is currently considered npm-supported when it has a valid root `package.json`.

npm provider behavior:
- architecture: `package.json` / workspaces driven
- code: `typescript-language-server` backed by TypeScript
- test:
  - authoritative Jest discovery via `jest --listTests` when available
  - heuristic fallback for other test setups
- quality: ESLint and Prettier

## Core Model

SuitCode uses shared typed objects across providers so the MCP and future higher-level flows can stay stable even when provider internals differ.

Important core concepts include:
- `Workspace`
- `Repository`
- `Component`
- `Runner`
- `PackageManager`
- `ExternalPackage`
- `FileInfo`
- `EntityInfo`
- `TestDefinition`
- repository/file/symbol/impact context models

Current runtime model:
- `Workspace` is a logical container for one or more supported repositories
- `Repository` owns provider instances and repository-scoped intelligence
- intelligence objects aggregate provider output by role

## MCP Server

SuitCode ships an MCP server under `src/suitcode/mcp` and exposes:
- tools
- resources
- prompts

The MCP server is intended to steer agents toward deterministic semantic tooling before manual exploration.

### Transports
- `stdio`
- HTTP (`/mcp`)

### Workspace Lifecycle
- workspaces are held in memory
- opening the same canonical repository root reuses the same workspace
- repository roots are unique across open workspaces in the same server process
- closing a workspace releases its repository ownership

## Installation

### Base install
```bash
python -m pip install -e .
```

### Development install
```bash
python -m pip install -e .[dev]
```

This installs:
- `pytest`
- `basedpyright`

## External Tooling

SuitCode intentionally reuses existing tools where appropriate.

### Python provider
Recommended tools:
- `basedpyright`
- `pytest`
- `ruff`

### npm provider
Recommended tools:
- `typescript-language-server`
- `typescript`
- `jest` for authoritative Jest test discovery
- `eslint`
- `prettier`

## Running the MCP Server

### Project-local launcher scripts
Windows:
```powershell
.\run_mcp.bat
```

Unix-like:
```bash
./run_mcp.sh
```

Both scripts:
- prefer the local `.venv`
- run in the foreground
- default to HTTP on `127.0.0.1:8000`
- pass through additional CLI args

Examples:
```powershell
.\run_mcp.bat --port 8011
```

```bash
./run_mcp.sh --port 8011
```

### Python module entrypoint
```bash
python -m suitcode.mcp.server --transport http --host 127.0.0.1 --port 8000
```

### Installed console script
```bash
suitcode-mcp --transport http --host 127.0.0.1 --port 8000
```

## MCP Tools

SuitCode currently exposes these MCP tools.

### Support and workspace lifecycle
- `list_supported_providers`
- `inspect_repository_support`
- `open_workspace`
- `list_open_workspaces`
- `get_workspace`
- `close_workspace`

### Workspace and repository access
- `list_workspace_repositories`
- `get_repository`
- `get_repository_by_path`
- `add_repository`

### Architecture
- `list_components`
- `list_aggregators`
- `list_runners`
- `list_package_managers`
- `list_external_packages`
- `list_files`
- `get_component_dependencies`
- `get_component_dependents`

### Code
- `find_symbols`
- `list_symbols_in_file`
- `find_definition`
- `find_references`

### Tests
- `list_tests`
- `get_related_tests`

### Quality
- `list_quality_providers`
- `lint_file`
- `format_file`

### Higher-level context and impact
- `repository_summary`
- `describe_components`
- `describe_files`
- `describe_symbol_context`
- `get_file_owner`
- `list_files_by_owner`
- `analyze_impact`

## MCP Tool Semantics

### Symbol matching
`find_symbols` and `list_symbols_in_file` use these rules:
- exact full match by default
- case-insensitive by default
- use `*` or `?` for glob matching
- set `is_case_sensitive=true` for case-sensitive exact or glob matching

### Definitions and references
`find_definition` and `find_references` return locations only.

Recommended flow:
1. use `find_definition` or `find_references`
2. use `list_symbols_in_file` on the returned path to enrich the file semantically
3. only then open the file manually if needed

### Test discovery provenance
`list_tests` and `get_related_tests` expose:
- `discovery_method`
- `discovery_tool`
- `is_authoritative`

This lets the agent distinguish tool-authoritative test discovery from heuristic fallback.

### Quality operations
Quality tools require an explicit `provider_id`.

Current quality providers:
- Python: Ruff
- npm: ESLint / Prettier

Quality results are compact and include:
- diagnostics
- changed flag
- applied fixes flag
- before/after content hashes
- symbol/entity delta

### Fail-fast behavior
SuitCode is intentionally fail-fast.

Examples:
- unsupported repositories fail on `open_workspace`
- invalid IDs or paths fail instead of being skipped
- malformed external tool output fails instead of being partially accepted
- ambiguous symbol or owner resolution fails instead of guessing

## MCP Resources

SuitCode currently exposes these resources:
- `suitcode://supported-providers`
- `suitcode://workspaces`
- `suitcode://workspace/{workspace_id}`
- `suitcode://workspace/{workspace_id}/repositories`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/architecture`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/tests`
- `suitcode://workspace/{workspace_id}/repository/{repository_id}/quality`

These are compact snapshots, not full data dumps.

## MCP Prompts

SuitCode currently exposes these prompts:
- `understand_repository_with_suitcode`
- `refactor_using_suitcode_tools`
- `apply_quality_fix_with_suitcode`

These prompts are short workflow guides meant to push the client toward SuitCode semantic tools before generic exploration.

## Recommended Agent Workflow

For a supported repository:
1. `inspect_repository_support`
2. `open_workspace`
3. `repository_summary`
4. use exact semantic tools:
   - `list_components`
   - `describe_components`
   - `describe_files`
   - `find_symbols`
   - `list_symbols_in_file`
   - `find_definition`
   - `find_references`
   - `get_related_tests`
   - `analyze_impact`
5. only then fall back to manual file exploration when needed

## Testing

Run the full test suite with:
```bash
python tests/run_all_tests.py -q
```

The project also includes focused provider, MCP, and fixture-based tests for:
- Python repositories
- npm repositories
- symbol queries
- definitions and references
- ownership and impact
- quality results
- MCP presentation and tool wiring

## Current Status

The project currently has:
- Python and npm providers
- repository-scoped intelligence
- an MCP server with semantic exploration tools
- tool-backed code intelligence
- partial authoritative test discovery
- tool-backed quality operations

What it does not currently depend on for normal runtime behavior:
- a persisted graph/database

## License / Project Notes

No license file is currently documented here.
If this project is intended for external distribution, add an explicit license and contribution policy.
