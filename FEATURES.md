# SuitCode Features

SuitCode is a deterministic repository intelligence product for coding agents.

This page is the short product summary. For installation and benchmark links, use [README.md](README.md). For research framing, use [docs/v1/RESEARCH.md](docs/v1/RESEARCH.md).

## Product Goal

SuitCode reduces structural uncertainty during coding work.

It answers a small set of high-value questions:
- what owns this repository or file
- what changes if I edit it
- what should I run before I trust the change
- what is unsupported or unavailable

The product is designed around deterministic evidence from the repository toolchain, not heuristics.

## Current Product Shape

Recommended MCP profile:
- `core`

Current core tools:
- `understand_repository`
- `understand_file`
- `what_changes_if_i_edit_this`
- `what_should_i_run`
- `can_i_do_this`

Two heavy tools support detail levels:
- `compact`: smallest curated answer
- `standard`: richer drill-down for up to 3 targets
- `full`: richest evidence payload for exactly 1 target

Default:
- `compact`

For very large single code files, `compact` may degrade to structural evidence to keep latency bounded.

## MCP Tools by Job

Repository orientation:
- `understand_repository`

File understanding:
- `understand_file`
- `what_changes_if_i_edit_this`

Deterministic validation planning:
- `what_should_i_run`

Feasibility and boundary checks:
- `can_i_do_this`

## What Users Get

### Repository understanding
- provider detection
- component and package boundaries
- deterministic ownership
- truth coverage and provenance visibility

### File and change understanding
- owner and nearby tests
- dependency and dependent surfaces
- exact reference-site previews when provider-backed references exist
- React/TSX render parent-child edges with explicit prop names
- provider-owned docs/spec structure

### Validation planning
- minimum deterministic validation set
- required validation separated from optional hygiene
- explicit exclusions when no deterministic surface exists
- narrower direct build/test surfaces preferred over broad dependent validation when both are provable

### Structured artifact support
- Markdown: sections, code blocks, links, frontmatter keys, checklist items
- OpenAPI / Swagger: paths, methods, operation IDs, schemas, tags

## Supported Today

Ecosystems and artifact families:
- `go`
- Python
- npm / TypeScript
- Go
- Markdown
- OpenAPI / Swagger

Agent integrations:
- Codex
- Claude Code
- Cursor

Analytics support:
- Codex live evaluation and passive analytics
- Claude/Cursor passive analytics

## Deterministic Execution Surfaces

SuitCode exposes execution-facing intelligence only when the repository toolchain proves it:
- deterministic test targets
- deterministic build targets
- deterministic runner targets
- deterministic lint and format targets where provider-owned quality tooling is resolvable

Evaluation and execution references:
- `scripts/EVALUATION.md`
- `docs/evaluation/benchmark_protocol_v1.md`

## Provenance and Trust Model

SuitCode keeps provenance attached to evidence-bearing answers and distinguishes:
- manifest-backed evidence
- syntax-backed structural evidence
- exact semantic/LSP-backed evidence
- explicit unsupported or unavailable boundaries

## Product Principles

- Deterministic first
- Provenance on evidence-bearing answers
- Compact by default
- Small tool surface for natural agent adoption
- Clear unsupported boundaries instead of guessed answers

## Current Limits

- `go.work` support is deferred
- structured docs/spec support is ownership and structure only, not semantic code linkage
- SuitCode does not expose generic shell execution as product intelligence
- live adoption and token-savings results are improving, but the current canonical benchmark still reflects an earlier broader tool surface

## Evidence Snapshot

Controlled Codex v7 benchmark:
- stable downstream A/B: `5/5` vs baseline `2/5`
- median turns per stable headline task: `3` vs `16`
- transcript-estimated visible tokens per stable headline task: `2793` vs `50956`

Evidence links:
- [docs/evidence/codex-v7/README.md](docs/evidence/codex-v7/README.md)
- [docs/v1/RESEARCH.md](docs/v1/RESEARCH.md)
