# SuitCode

SuitCode is a repository intelligence engine with an MCP server front-end.

Its job is to replace broad repository exploration with deterministic semantic tools.

SuitCode is built for questions like:
- What are the real components, runners, package managers, and external dependencies in this repository?
- What does this component depend on, and what depends on it?
- Which files belong to this component, runner, package manager, or test target?
- Which symbols exist in this file or across the repository?
- Where is this symbol defined, and where is it referenced?
- Which tests cover this file, symbol, or component?
- Was that test information discovered from a real tool or from a heuristic fallback?
- What likely breaks if I change this file, symbol, or owner, given component dependents, references, and related tests?

That is the current value proposition: architecture understanding, code navigation, test targeting, and impact estimation through deterministic tools.

The near-term direction is:
- make provenance explicit everywhere, not only for selected outputs
- compose high-level change analysis from provider-backed evidence
- expose deterministic action surfaces so agents can run the right tests, runners, and builds without guessing commands

## What SuitCode Can Do Today

For a supported repository, SuitCode can expose:
- real architecture nodes:
  - components
  - aggregators
  - runners
  - package managers
  - external packages
- file ownership:
  - which owner owns a file
  - which files belong to an owner
- code intelligence:
  - repository-wide symbol lookup
  - file-local symbol lookup
  - definition lookup
  - reference lookup
- test intelligence:
  - discovered test targets
  - related tests for a file or owner
  - discovery provenance: authoritative vs heuristic
- quality intelligence:
  - available quality providers
  - linting
  - formatting
  - diagnostics and symbol deltas
- higher-level context:
  - repository summary
  - component context
  - file context
  - symbol context
  - impact analysis

Concretely, SuitCode already supports:
- real components and targets plus their dependencies
- component dependents for blast-radius analysis
- related tests for a component, file, symbol, or owner
- enough test metadata to narrow to the right test targets instead of exploring test directories manually
- impact summaries that combine ownership, references, component dependents, and related tests

## Supported Provider Families

Current supported providers:
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
- SuitCode prefers real toolchains, servers, and protocols over custom reimplementation whenever practical

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

Python repository intelligence currently supports:
- top-level packaged components from `pyproject.toml`
- repo-level dependency modeling from `pyproject.toml`
- LSP-backed symbol, definition, and reference lookup
- related-test lookup against discovered Python test targets
- impact summaries for files, symbols, and owners

### npm
A repository is currently considered npm-supported when it has a valid root `package.json`.

npm provider behavior:
- architecture: `package.json` / workspaces driven
- code: `typescript-language-server` backed by TypeScript
- test:
  - authoritative Jest discovery via `jest --listTests` when available
  - heuristic fallback for other test setups
- quality: ESLint and Prettier

npm repository intelligence currently supports:
- workspace/package components and their internal/external dependencies
- dependents across workspace components
- LSP-backed symbol, definition, and reference lookup for JS/TS
- related-test lookup for package-scoped files and owners
- impact summaries for files, symbols, and owners

## Core Runtime Model

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

The important constraint is:
- provider internals are allowed to differ
- the agent-facing object model stays consistent

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

Once the server is running, agents can connect to `/mcp` and use the semantic tool surface instead of starting with filesystem exploration.

## External Tools SuitCode Reuses

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

These tools are not the public interface.
The public interface is the MCP tool surface and the shared SuitCode result types.

## MCP Tools

SuitCode currently exposes these MCP tools.

### Support and workspace lifecycle
- `list_supported_providers`
  Answers:
  - What ecosystems and intelligence roles does SuitCode support at all?
- `inspect_repository_support`
  Answers:
  - Is this repository supported before I try to open it?
  - Which provider would handle it?
- `open_workspace`
  Answers:
  - Open this supported repository for semantic work and give me stable IDs.
- `list_open_workspaces`
  Answers:
  - Which workspaces are already open in this MCP server?
- `get_workspace`
  Answers:
  - What is this workspace and which repositories does it contain?
- `close_workspace`
  Answers:
  - Close this workspace and release its repository ownership.

### Workspace and repository access
- `list_workspace_repositories`
  Answers:
  - Which repositories are inside this workspace?
- `get_repository`
  Answers:
  - Give me the exact repository metadata for this repository ID.
- `get_repository_by_path`
  Answers:
  - Which tracked repository corresponds to this path?
- `add_repository`
  Answers:
  - Add this supported repository into the workspace and give me its stable ID.

### Architecture
- `list_components`
  Answers:
  - What are the real architecture components in this repository?
- `list_aggregators`
  Answers:
  - Are there architecture-level orchestration targets here?
- `list_runners`
  Answers:
  - What runnable targets or entrypoints exist in this repository?
- `list_package_managers`
  Answers:
  - Which package managers or ecosystem managers does this repository use?
- `list_external_packages`
  Answers:
  - What external dependencies does this repository declare?
- `list_files`
  Answers:
  - Which files does SuitCode currently understand and own semantically?
- `get_component_dependencies`
  Answers:
  - What does this component depend on?
- `get_component_dependents`
  Answers:
  - What depends on this component?
  - What is the likely architecture blast radius if I change it?

### Code
- `find_symbols`
  Answers:
  - Where does a symbol with this exact name exist in the repository?
  - Which symbols match this glob if I use `*` or `?`?
- `list_symbols_in_file`
  Answers:
  - Which symbols exist in this specific file?
  - Does this file define the symbol I care about?
- `find_definition`
  Answers:
  - Where is this symbol or file position defined?
- `find_references`
  Answers:
  - Where is this symbol or file position referenced?
  - What code locations are affected if I change it?

### Tests
- `list_tests`
  Answers:
  - What test targets exist in this repository?
  - Were those tests discovered authoritatively or heuristically?
- `get_related_tests`
  Answers:
  - Which tests cover this file or owner?
  - If I change this component or file, which tests should I look at first?
  - Can I narrow to only the relevant test targets?

### Quality
- `list_quality_providers`
  Answers:
  - Which quality provider can lint or format files in this repository?
- `lint_file`
  Answers:
  - What lint diagnostics does this file currently have?
  - What changes if I apply lint fixes?
- `format_file`
  Answers:
  - What changes if I format this file now?

### Higher-level context and impact
- `repository_summary`
  Answers:
  - Give me a compact first-pass summary of this repository.
  - What kind of system is this before I start exploring files?
- `describe_components`
  Answers:
  - For these exact components, what files, runners, tests, dependencies, and dependents matter?
- `describe_files`
  Answers:
  - For these exact files, who owns them, what symbols do they contain, and which tests are related?
- `describe_symbol_context`
  Answers:
  - For this exact symbol, who owns it, where is it defined, where is it referenced, and which tests are related?
- `get_file_owner`
  Answers:
  - Which component, runner, package manager, or test target owns this file?
- `list_files_by_owner`
  Answers:
  - Which files belong to this exact component, runner, package manager, or test target?
- `analyze_impact`
  Answers:
  - What breaks if I change this file, symbol, or owner?
  - Given build graph, references, ownership, and related tests, what is the likely impact?

## What Those MCP Tools Let An Agent Do

### First-pass repository understanding
Use:
1. `inspect_repository_support`
2. `open_workspace`
3. `repository_summary`
4. `list_components`
5. `describe_components`

This gives:
- the supported provider(s)
- repository structure
- primary components and targets
- dependency and dependent previews
- related tests and owned files

### File understanding without opening the file first
Use:
1. `get_file_owner`
2. `describe_files`
3. `list_symbols_in_file`

This gives:
- who owns the file
- which tests are related
- which symbols are inside it
- which quality provider applies

### Code navigation
Use:
1. `find_symbols`
2. `list_symbols_in_file`
3. `find_definition`
4. `find_references`

This gives:
- exact symbol lookup
- file-local symbol context
- definition locations
- reference locations

### Real components and targets plus their deps
Use:
1. `list_components`
2. `describe_components`
3. `get_component_dependencies`
4. `get_component_dependents`

This answers:
- what the real architecture targets are
- what each one depends on
- what depends on it
- which files, runners, and tests are attached to it

### Test targeting
Use:
1. `list_tests`
2. `get_related_tests`
3. `describe_components` or `describe_files`

This answers:
- which tests exist
- which tests are related to a file or component
- whether discovery came from a real tool or a heuristic fallback
- enough information to run only the relevant test targets yourself

SuitCode does not currently execute test targets for you.
Its current role is to identify the relevant targets and test files so the agent can run only the right subset.

### What breaks if I change X
Use:
1. `get_component_dependencies`
2. `get_component_dependents`
3. `find_references`
4. `get_related_tests`
5. `analyze_impact`

This answers:
- what this component depends on
- what depends on it
- where the symbol or file is referenced
- which tests are likely relevant
- the likely blast radius of a change to a file, symbol, or owner

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

This matters because SuitCode already supports:
- real pytest-based discovery when available
- real Jest-based discovery when available
- explicit heuristic fallback when the authoritative tool path is not available

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

## Current Status

The project currently has:
- Python and npm providers
- repository-scoped intelligence
- an MCP server with semantic exploration tools
- tool-backed code intelligence
- partial authoritative test discovery
- tool-backed quality operations
- component dependency and dependent traversal
- file, symbol, and owner context
- impact analysis that combines ownership, references, and related tests

What it does not currently depend on for normal runtime behavior:
- a persisted graph/database
