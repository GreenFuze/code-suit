# Current Contributions of SuitCode

This document records the current research and system contributions of SuitCode as of March 2026.

The emphasis here is on what the current system contributes technically and methodologically, not on future aspirations.

## 1. A Deterministic Repository-Intelligence Formulation For Coding Agents

SuitCode contributes a concrete formulation of repository intelligence centered on deterministic evidence sources:
- manifests and workspace metadata
- build and test toolchains
- language servers
- quality providers
- explicit structured artifacts such as Markdown and OpenAPI

The contribution is not “agents can use repo tools.” The contribution is a stricter contract:
- answer with provider-backed evidence when available
- return explicit unsupported or excluded results when not available
- keep provenance attached to evidence-bearing outputs

This formulation makes repository intelligence auditable in a way that generic search-first or summary-first systems are not.

## 2. A Small Task-Shaped MCP Interface As A Product And Research Contribution

SuitCode's current recommended interface is a small core tool set:
- `understand_repository`
- `understand_file`
- `what_changes_if_i_edit_this`
- `what_should_i_run`
- `can_i_do_this`

This is itself a contribution.

The project began with a larger, lower-level tool inventory. The current system contributes the design claim that **interface shape matters for live adoption**. In other words, repository intelligence is not only a data problem; it is also an agent-tooling problem.

The core profile represents a research-backed move from:
- lifecycle-heavy, decomposed tooling

to:
- direct task-question tools with compact defaults

## 3. Minimum Verified Change Set As A First-Class Primitive

SuitCode contributes a deterministic operational primitive: the **minimum verified change set**.

Instead of returning generic advice, the system computes the smallest provider-backed set of:
- tests
- build targets
- runner actions
- quality validation operations
- optional hygiene operations
- explicit exclusions

The current system also contributes a narrowing policy for shared targets:
- direct owner/build/test surfaces take precedence over broader dependent validation when both are provable
- broader dependent validation is included only when narrower direct validation does not exist

This is a practical contribution because it turns repository intelligence into bounded validation planning rather than merely explanation.

## 4. Cross-Provider Separation Of Responsibilities

SuitCode contributes a clean architectural split:
- providers produce raw deterministic evidence in their own ecosystem
- SuitCode core performs generic aggregation, preview ranking, exclusion policy, and validation minimization

This split is important because it prevents two common failures:
- pushing generic product policy into ecosystem-specific providers
- weakening determinism by letting aggregation logic drift into heuristics

The current system therefore contributes not only features, but also a reusable layering rule for multi-provider agent tooling.

## 5. Structured Artifacts As First-Class Deterministic Surfaces

SuitCode contributes deterministic support for non-code artifacts without pretending they are code.

Current examples:
- Markdown
- OpenAPI / Swagger

These artifacts now support:
- ownership
- structure extraction
- explicit non-validation behavior
- owned-but-empty impact when no code impact is provable

This is a useful contribution because mixed change sets in real repositories often span:
- executable code
- tests
- specs
- documentation

SuitCode's current artifact model handles those files honestly instead of failing noisily or inventing executable semantics.

## 6. Deterministic Frontend UI-Wiring Intelligence

SuitCode contributes provider-backed frontend intelligence that remains inside strict deterministic boundaries.

Current npm / TypeScript contributions include:
- local React/TSX render parent-child edges
- explicit prop names at JSX render sites
- exact reference-site previews where provider-backed references exist
- narrow TS/TSX invariant findings only when the type checker and local AST can prove them
- narrow local static flow summaries only for direct symbol-backed edges

This is an important contribution because frontend coding work often depends on local UI wiring, but many available tools either stay too shallow or become heuristic too quickly.

## 7. Deterministic Go Impact Enrichment Beyond Package Imports

For Go, SuitCode contributes a deterministic combination of:
- `go list`-derived architecture and package surfaces
- package-level test/build actions
- `gopls`-backed symbol, reference, and implementation evidence

The important contribution is not generic “Go support.” It is that SuitCode can enrich impact analysis with implementation candidates while keeping those candidates separate from direct dependency edges.

That separation preserves epistemic clarity:
- direct imports and references are stronger evidence
- implementation candidates are deterministic but weaker and therefore represented separately

## 8. Truth Coverage And Provenance As User-Facing Outputs

SuitCode contributes a repository-intelligence system that makes epistemic status explicit.

It does this through:
- provenance fields on evidence-bearing outputs
- repository and change-local truth coverage summaries
- explicit degraded or unavailable states

This contribution matters for both research and product reasons:
- it allows evaluation of what the system actually knows
- it prevents unsupported surfaces from being silently folded into confident answers

## 9. Evaluation And Analytics Infrastructure That Separates Lab And Live Evidence

SuitCode contributes an evaluation stack that distinguishes:
- controlled benchmark evidence
- deterministic execution evidence
- passive adoption analytics
- live usage analytics
- transcript-estimated token accounting

The important methodological contribution is the separation of evidence classes.

The current repository explicitly distinguishes:
- benchmark A/B claims
- calibration results
- stress results
- live analytics

That distinction made it possible to notice the central product lesson of this phase: benchmark success did not automatically imply healthy live adoption.

## 10. A Research Direction: Interface Shape As Part Of Repository Intelligence

The most important current contribution may be conceptual.

SuitCode now treats interface shape as part of the repository-intelligence problem. The system's present direction argues that:
- deterministic evidence quality matters
- compactness matters
- early tool discoverability matters
- task-shaped questions matter
- the tool surface itself affects token savings and adoption

That is a stronger claim than the initial version of the project made.

## Scope Of These Contributions

These contributions should be read with the following boundaries.

They do not claim:
- broad semantic understanding of repository intent
- heuristic bug prediction
- generic shell planning as deterministic intelligence
- full whole-program correctness analysis
- publication-grade external validity across all agents and repositories

They do claim:
- a concrete deterministic repository-intelligence architecture
- a compact agent-facing tool surface shaped by live adoption lessons
- a reusable split between provider evidence and core policy
- explicit support for validation planning, impact analysis, and structured non-code artifacts

## Current Supporting Documents

- [README.md](../../README.md)
- [FEATURES.md](../../FEATURES.md)
- [docs/v1/RESEARCH.md](RESEARCH.md)
- [docs/evidence/codex-v7/README.md](../evidence/codex-v7/README.md)
- [canonical March 19 comparison](../../.suit/evaluation/codex/comparisons/2026-03-19T10-54-59Z__codex-comparison-7e510e57620f40509ee4a01f5f86094f/comparison.md)
