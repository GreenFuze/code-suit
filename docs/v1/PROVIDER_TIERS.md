# Provider Code Intelligence Tiers

SuitCode code providers expose deterministic evidence through three compute tiers.

## Tier 1: Structural

Structural evidence is the fast broad-orientation tier.

Provider requirements:
- Use syntax, manifests, or local file analysis only.
- Do not require language-server workspace warmup.
- Do not perform file-wide reference, definition, or implementation walks.
- Return sparse output rather than guessing.
- Use `SourceKind.SYNTAX` provenance for syntax-derived symbols.

Provider hooks:
- `list_structural_symbols_in_file(...)`
- `get_structural_file_relationships(...)`

Current examples:
- Go uses a bundled `go/parser` helper for top-level symbols.
- NPM uses TypeScript compiler AST symbol extraction.
- Python uses stdlib `ast` for classes, functions, methods, and module assignments.

## Tier 2: Semantic

Semantic evidence is the exact focused-operation tier.

Provider requirements:
- Use LSP, compiler APIs, typechecker APIs, or exact deterministic provider evidence.
- Keep exact reference/definition/implementation operations focused.
- Degrade runtime capability when provider-backed coverage is unavailable or non-functional.

Provider hooks:
- `get_symbol(...)`
- `list_symbols_in_file(...)`
- `find_definition(...)`
- `find_references(...)`
- `find_implementations(...)`
- `get_file_implementation_locations(...)`

Current examples:
- Go uses `gopls` for exact definitions, references, and implementations.
- NPM uses TypeScript language-server/tooling plus exact TypeScript helper probes.
- Python uses basedpyright for semantic code intelligence.

## Tier 3: Indexed

Indexed evidence is the future persistent/background tier.

No provider implements this tier yet. Future providers may add precomputed symbol/reference indexes as an optimization, but MCP tool semantics must remain deterministic and compatible with Tier 1/Tier 2 behavior.

## Core Routing Rule

Broad multi-file compact tools use Tier 1 by default:
- `understand_file(detail_level="compact")` with more than 3 targets
- `what_changes_if_i_edit_this(detail_level="compact")` with more than 3 targets

Focused compact calls and `standard`/`full` calls may use Tier 2.

## Determinism Boundaries

Do not add:
- semantic hotspot inference
- guessed root-cause labels
- fuzzy symbol matching beyond existing query semantics
- roadmap/doc status classification
- runtime/manual-QA claims

If evidence is weak, return sparse output or degrade the relevant runtime capability.
