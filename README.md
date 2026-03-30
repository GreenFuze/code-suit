# SuitCode

**Deterministic repository intelligence for coding agents.**

SuitCode is an MCP server that answers repository questions through the toolchain the repository already defines: manifests, builds, tests, language servers, quality tools, and explicit structured artifacts.

The goal is not to help an agent search faster. The goal is to reduce uncertainty earlier:
- who owns this file
- what changes if I edit it
- what is the minimum deterministic validation set
- where SuitCode's knowledge stops

## Why SuitCode Exists

General code-search and repo-map tools are good at finding text. They are weaker at answering operational questions such as:
- what actually owns this file
- which exact tests are justified
- which build target is the narrowest safe validation
- whether a doc/spec file has no executable validation surface at all

SuitCode answers those questions with explicit provenance instead of heuristics.

## The Current Product Shape

SuitCode now ships with two MCP profiles:
- `core`: the recommended agent-facing surface
- `full`: the larger expert and research surface

The current design direction is deliberate: a small set of task-shaped tools works better in practice than a large inventory of low-level tools.

### Core tools

- `understand_repository`
- `understand_file`
- `what_changes_if_i_edit_this`
- `what_should_i_run`
- `can_i_do_this`

These are the default entry points for agents.

### Heavy-tool detail levels

Two core tools support `detail_level`:
- `understand_file`
- `what_changes_if_i_edit_this`

Levels:
- `compact`: smallest curated deterministic answer
- `standard`: bounded richer answer
- `full`: richest evidence payload

Default:
- `compact`

### Multi-file support

The target-bearing core tools accept `repository_rel_paths` as a list.

That means one call can cover a local change set and return:
- per-target detail
- one ranked and capped aggregate view

## What SuitCode Can Do Today

### Deterministic repository understanding

SuitCode can identify:
- supported providers for a repository
- owned components and package boundaries
- deterministic file ownership
- explicit dependency and dependent surfaces
- repository truth coverage and provenance availability

### Deterministic impact analysis

SuitCode can answer:
- what depends on this file
- exact reference-site previews when provider-backed references exist
- UI render parent/child edges for local React/TSX components
- explicit prop names passed at JSX call sites
- Go implementation candidates when `gopls` can prove them
- owned-but-empty impact for docs/spec artifacts when no code edge is provable

### Deterministic validation planning

SuitCode can produce a minimum verified change set that separates:
- required validation
- optional hygiene
- explicit exclusions

It prefers narrower direct owner/build/test surfaces over broader dependent validation when both are provable.

### Structured artifact support

SuitCode now treats common non-code artifacts as first-class deterministic surfaces.

Markdown:
- deterministic ownership
- section hierarchy and line ranges
- fenced code blocks
- links
- frontmatter keys and ranges
- checklist items

OpenAPI / Swagger:
- deterministic ownership for well-known filenames
- spec version
- paths and methods
- operation IDs
- component schema names
- top-level tags

For provider-owned docs/spec files:
- `understand_file` returns structure
- `what_changes_if_i_edit_this` returns ownership plus empty impact when no code impact is provable
- `what_should_i_run` returns explicit non-validation exclusions instead of a hard failure

## Supported Ecosystems

Current provider support:
- Python
- npm / TypeScript
- Go
- Markdown
- OpenAPI / Swagger

Current frontend/npm support includes:
- workspace and standalone package detection
- deterministic ownership of package source and `public/` assets
- TypeScript symbol/reference intelligence
- React render/prop-flow edges
- narrow TS/TSX invariant and local-flow findings when the checker can prove them

Current Go support includes:
- `go list`-backed architecture
- package-level `go test` and build targets
- `gopls`-backed symbols, definitions, references, and implementation candidates
- multi-module repos without `go.work`

## What Makes It Different

SuitCode is intentionally strict.

It will:
- return explicit exclusions when a validation surface does not exist
- keep provenance on evidence-bearing answers
- distinguish direct deterministic surfaces from weaker derived ones
- avoid inventing cross-layer links it cannot prove

It will not:
- expose generic shell execution as product intelligence
- guess unsupported actions
- pretend docs/spec files are executable when they are not
- blur deterministic evidence with semantic summarization

## Current Evidence

Controlled Codex v7 A/B benchmark:
- stable downstream A/B: SuitCode `5/5` vs baseline `2/5`
- median turns per stable headline task: SuitCode `3` vs baseline `16`
- stable execution A/B: SuitCode `2/2` vs baseline `0/2`
- transcript-estimated visible tokens per stable headline task: SuitCode `2793` vs baseline `50956`

![Headline outcomes](docs/evidence/codex-v7/figures/01-headline-outcomes.svg)

Primary evidence links:
- [Codex v7 evidence summary](docs/evidence/codex-v7/README.md)
- [Canonical comparison report](.suit/evaluation/codex/comparisons/2026-03-19T10-54-59Z__codex-comparison-7e510e57620f40509ee4a01f5f86094f/comparison.md)

Important interpretation:
- the benchmark demonstrates that deterministic task-shaped repo intelligence can outperform baseline exploration on bounded tasks
- it does not, by itself, prove natural live adoption
- recent product work has therefore focused on smaller core tools, compact defaults, and better live agent fit

## Install

Primary install path:

```bash
pipx install git+https://github.com/GreenFuze/suit-code.git
```

Secondary install path:

```bash
uv tool install git+https://github.com/GreenFuze/suit-code.git
```

Installed entrypoints:
- `suitcode-mcp-core`
- `suitcode-mcp --profile core`
- `suitcode-mcp --profile full`
- `suitcode-install`

Repository launchers in a source checkout:
- Windows: `run_mcp.bat`
- macOS/Linux: `run_mcp.sh`

The repository launchers default to `core`.

Current installer note:
- `suitcode-install` still wires `suitcode-mcp`
- if you want the recommended smaller default surface today, point your agent at `suitcode-mcp-core` or the repository launchers

## Connect To Your Agent

### Codex

Install:

```bash
suitcode-install --agent codex
```

Verify:

```bash
codex mcp list
```

Manual fallback on Windows `~/.codex/config.toml`:

```toml
[mcp_servers.suitcode]
transport = "stdio"
command = "cmd"
args = ["/c", "suitcode-mcp-core"]
enabled = true
```

Manual fallback on macOS/Linux `~/.codex/config.toml`:

```toml
[mcp_servers.suitcode]
transport = "stdio"
command = "suitcode-mcp-core"
args = []
enabled = true
```

### Claude Code

Install:

```bash
suitcode-install --agent claude
```

Manual fallback on Windows:

```bash
claude mcp add --transport stdio --scope user suitcode -- cmd /c suitcode-mcp-core
```

Manual fallback on macOS/Linux:

```bash
claude mcp add --transport stdio --scope user suitcode -- suitcode-mcp-core
```

### Cursor

Install:

```bash
suitcode-install --agent cursor
```

Manual fallback on Windows `%USERPROFILE%\\.cursor\\mcp.json`:

```json
{
  "mcpServers": {
    "suitcode": {
      "command": "cmd",
      "args": ["/c", "suitcode-mcp-core"]
    }
  }
}
```

Manual fallback on macOS/Linux `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "suitcode": {
      "command": "suitcode-mcp-core",
      "args": []
    }
  }
}
```

## Example Workflow

Prompt:

> A bug report points at one file. What owns it, what should I inspect first, and what exact validation set should run before I trust a fix?

A typical SuitCode flow is:
1. `understand_repository`
2. `understand_file`
3. `what_changes_if_i_edit_this`
4. `what_should_i_run`

That keeps the agent on direct task questions instead of broad manual exploration.

Example:
- [Bug Report To Validation](docs/examples/bug-report-to-validation.md)

## Where To Read More

- [FEATURES.md](FEATURES.md) for the current product feature summary
- [docs/v1/RESEARCH.md](docs/v1/RESEARCH.md) for the research trajectory and why the product changed direction
- [docs/v1/CONTRIBUTION.md](docs/v1/CONTRIBUTION.md) for the current research contributions of SuitCode
- [LICENSE.md](LICENSE.md)
