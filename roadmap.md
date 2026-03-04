# SuitCode Roadmap

This file tracks the next implementation phases for SuitCode.

It is an engineering backlog, not a strategy essay. Each phase is intentionally small, capability-driven, and ends with refactor, object-oriented design review, fail-fast review, and tests.

## Guiding Principles

- [ ] Toolchain-backed truth first
  - Answers should come from the real manifest, build system, LSP, BSP, test tool, or quality tool where possible.
- [ ] Prefer existing tools and protocols
  - Reuse LSP, BSP, test runners, build-system CLIs, and quality tools before writing custom logic.
- [ ] Heuristics are explicit fallback only
  - Heuristic output must never be presented as equivalent to authoritative output.
- [ ] Provenance must be visible
  - High-value answers should say how they were derived.
- [ ] Deterministic actions over guessed commands
  - If SuitCode can identify a real runnable surface, it should expose the exact action so the agent does not infer commands manually.
- [ ] No persisted graph by default
  - Use ad hoc projections and typed objects unless a concrete pain point justifies more.
- [ ] Small phases only
  - Each phase should be narrow and shippable.
- [ ] Every phase ends with refactor plus tests
  - No feature phase is complete without deduplication, OO boundary review, fail-fast review, and tests.

## Roadmap Rules

- [ ] Every phase includes:
  - capability work
  - refactor / design hardening
  - tests / acceptance
- [ ] Public output contracts stay typed and explicit.
- [ ] Provider truth must not be replaced by guessed indexing.
- [ ] Existing tools and protocols must be preferred before custom implementation is accepted.
- [ ] If a real tool exists and is practical, the burden is on the custom implementation to justify itself.
- [ ] Any ambiguity discovered during implementation must be resolved in Plan Mode before coding.
- [ ] No phase is done if it increases duplication or weakens object boundaries.
- [ ] No action tool may be a generic shell wrapper; actions must be provider-backed and deterministic.

## Phase 1: Universal Provenance

### Goal
Make provenance a first-class, consistent concept across SuitCode instead of scattered per-feature metadata.

### Capability work
- [ ] Add a shared provenance model used across:
  - architecture outputs
  - dependency outputs
  - related-test outputs
  - impact outputs
  - quality outputs where appropriate
  - future action outputs
- [ ] Normalize core provenance concepts:
  - `confidence_mode`
  - `source_kind`
  - `source_tool`
  - short explanation / evidence summary
- [ ] Attach provenance to:
  - dependencies
  - component context
  - file context
  - symbol context
  - impact outputs

### Refactor / design hardening
- [ ] Remove duplicated provenance-like fields where they exist in ad hoc forms.
- [ ] Ensure provenance is added in the correct layer:
  - provider-native evidence at provider/internal translation layer
  - cross-provider joins at intelligence/core layer
  - presentation-only shaping at MCP presenter layer
- [ ] Review OO boundaries so provenance assembly is not duplicated across providers and MCP presenters.

### Tests / acceptance
- [ ] Add tests for provenance consistency across:
  - authoritative outputs
  - derived outputs
  - heuristic fallback outputs
- [ ] Add fail-fast tests for missing or contradictory provenance.
- [ ] Add MCP tests to ensure provenance reaches the agent intact.

### Done when
- [ ] Provenance is a shared typed concept.
- [ ] Heuristic vs authoritative is not special-cased per feature anymore.
- [ ] Every high-value answer class can explain where it came from.

## Phase 2: ChangeImpact North-Star Artifact

### Goal
Introduce one high-value composed artifact that answers:
- what owns this
- what depends on it
- what symbols are involved
- what tests matter
- what runners matter
- what quality gates apply
- why

### Capability work
- [ ] Add a first-class `ChangeImpact` or `ChangeAnalysis` model.
- [ ] Add a new MCP tool, likely `analyze_change`, or evolve `analyze_impact` into the north-star artifact if that keeps naming cleaner.
- [ ] Include:
  - owner
  - primary component
  - dependent components
  - code references
  - related tests
  - related runners
  - quality providers / required gates
  - provenance per contributing category

### Refactor / design hardening
- [ ] Avoid bloating `Repository` or one MCP service with the full composition logic.
- [ ] Introduce dedicated orchestration objects if needed:
  - `ChangeImpactService`
  - `ChangeEvidenceAssembler`
- [ ] Reuse existing context and reference services instead of duplicating logic.

### Tests / acceptance
- [ ] Add representative file target coverage.
- [ ] Add representative symbol target coverage.
- [ ] Add representative owner target coverage.
- [ ] Add explicit failure coverage for unresolved targets.
- [ ] Add provenance coverage for each contributing evidence type.

### Done when
- [ ] SuitCode exposes one high-level change artifact.
- [ ] The output is factual, deterministic, and provenance-backed.
- [ ] It does not pretend to be an execution plan yet.

## Phase 3: Action Model Foundation

### Goal
Introduce a typed, provider-backed action model so SuitCode can expose real executable surfaces instead of forcing agents to infer commands.

### Capability work
- [ ] Add shared action/result types for deterministic actions such as:
  - test execution
  - runner execution
  - build execution
- [ ] Model action concepts explicitly, for example:
  - action kind
  - provider
  - target ID
  - command / invocation
  - working directory
  - provenance
  - dry-run capability if applicable
- [ ] Add a way to represent what actions are available for this repository, component, runner, or test target.

### Refactor / design hardening
- [ ] Keep actions separate from pure intelligence outputs.
- [ ] Do not leak raw shell/process concepts directly into MCP DTOs.
- [ ] Introduce provider-native action abstractions instead of scattering command rendering through providers and MCP layers.
- [ ] Enforce OO separation between:
  - discovery
  - context
  - execution rendering
  - execution results

### Tests / acceptance
- [ ] Add action model validation tests.
- [ ] Add fail-fast tests for unsupported targets.
- [ ] Add provenance tests for action outputs.
- [ ] Verify no generic shell-execution abstraction slips in.

### Done when
- [ ] SuitCode has a typed foundation for deterministic actions.
- [ ] Future test/build/run tools can be added without inventing ad hoc command payloads.

## Phase 4: Test Execution Guidance and Actions

### Goal
Turn related tests into a deterministic executable answer:
- what tests cover this
- how do I run only those
- optionally run them through SuitCode

### Capability work
- [ ] Add exact run instructions for discovered test targets.
- [ ] Add a test-target context model or tool, likely `describe_test_target` and/or `how_to_run_related_tests`.
- [ ] Add a test action tool, likely `run_test_target`.
- [ ] For each supported framework, return:
  - exact runnable command pattern
  - whether the target is authoritative or heuristic
  - narrowed file/target scope when deterministic
- [ ] Prefer existing test tools:
  - pytest
  - jest
  - future framework-specific tools when supported

### Refactor / design hardening
- [ ] Separate:
  - test discovery
  - test relation logic
  - test execution rendering
  - test execution actions
- [ ] Keep command construction framework-specific and OO, not scattered string building.
- [ ] Avoid provider duplication by introducing shared test execution formatting helpers where appropriate.

### Tests / acceptance
- [ ] Add pytest authoritative run guidance coverage.
- [ ] Add jest authoritative run guidance coverage.
- [ ] Add `run_test_target` structured result tests.
- [ ] Keep heuristic fallback cases clearly marked.
- [ ] Add fail-fast tests for malformed or unsupported execution metadata.

### Done when
- [ ] The agent can ask how to run only the relevant tests and get a deterministic answer.
- [ ] The agent can invoke a real test target through a provider-backed action.
- [ ] The result distinguishes authoritative from heuristic narrowing.

## Phase 5: Runner Context and Operational Actions

### Goal
Make runners first-class operational intelligence and executable surfaces rather than just listed nodes.

### Capability work
- [ ] Add runner context, likely `describe_runner`.
- [ ] Answer:
  - what this runner is
  - what component owns it
  - what files back it
  - what tests relate to it
  - how it is invoked
- [ ] Add runner action tooling, likely `run_runner`.
- [ ] Ensure actions expose exact invocations for:
  - npm scripts / workspace runners
  - python entry-point runners

### Refactor / design hardening
- [ ] Centralize runner ownership and entrypoint resolution logic.
- [ ] Avoid duplicate runner-context assembly between providers.
- [ ] Keep architecture metadata and executable invocation semantics separated cleanly.
- [ ] Ensure provider-native runner execution is modeled, not improvised per call site.

### Tests / acceptance
- [ ] Add npm runner context and execution tests.
- [ ] Add python runner context and execution tests.
- [ ] Add fail-fast coverage for unknown runner IDs.
- [ ] Verify no duplicated runner-resolution logic across providers.

### Done when
- [ ] Runner questions no longer require combining multiple separate tools manually.
- [ ] The agent can invoke known runner targets deterministically.

## Phase 6: Build and Project Actions

### Goal
Expose real build/project actions so the agent does not have to guess how to build or validate the project.

### Capability work
- [ ] Add project/build action discovery, likely `list_project_actions` and/or provider-specific action discovery under a generic action model.
- [ ] Add build action tooling, likely `build_project` and `build_target`.
- [ ] Prefer existing build/system tools, for example:
  - npm workspace build scripts where authoritative
  - python project build tools only where there is a real deterministic build surface
  - future BSP/build-graph integrations where available
- [ ] Return structured action results:
  - status
  - command used
  - working directory
  - affected target
  - provenance

### Refactor / design hardening
- [ ] Keep build actions provider-backed.
- [ ] Do not implement guessed best-effort build commands.
- [ ] Separate:
  - action discovery
  - action execution
  - action result interpretation

### Tests / acceptance
- [ ] Add deterministic build-action discovery tests.
- [ ] Add provider-specific build action tests.
- [ ] Add fail-fast tests for unsupported repositories or targets.
- [ ] Verify no generic shell-wrapper behavior.

### Done when
- [ ] The agent can ask how to build this project or target and get a deterministic answer.
- [ ] The agent can invoke that build through SuitCode when supported.

## Phase 7: Generic LSP Backend Family

### Goal
Stop duplicating code-role plumbing per ecosystem by separating:
- ecosystem/build-system provider
- code backend mechanism

### Capability work
- [ ] Introduce a generic LSP-backed code backend family or internal abstraction.
- [ ] Move shared code-navigation logic out of ecosystem-specific providers.
- [ ] Keep ecosystem-specific responsibility limited to:
  - server/tool resolution
  - file-type filtering
  - backend-specific initialization quirks
- [ ] Explicitly prefer LSP before any custom code navigation implementation.

### Refactor / design hardening
- [ ] Refactor current `python` and `npm` code-role logic onto the shared backend abstraction.
- [ ] Remove duplicated symbol/definition/reference translation and filtering patterns where possible.
- [ ] Keep the abstraction narrow enough to avoid overengineering.

### Tests / acceptance
- [ ] Preserve behavior for:
  - `find_symbols`
  - `list_symbols_in_file`
  - `find_definition`
  - `find_references`
- [ ] Keep provider-specific quirks covered.
- [ ] Preserve fail-fast behavior for missing LSP/tool resolution.

### Done when
- [ ] Adding a new LSP-backed language does not require copying the current provider code-role pattern.

## Phase 8: Build-Graph-Native Architecture Expansion

### Goal
Move architecture deeper into real build truth for ecosystems where manifest truth is not enough.

### Capability work
- [ ] Start with one concrete build-graph-native ecosystem at a time, for example:
  - Cargo
  - CMake
  - Bazel
  - MSBuild
- [ ] Prefer existing standards and tooling:
  - BSP where it is real and useful
  - native build graph/query tools where they are the true source of truth

### Refactor / design hardening
- [ ] Keep architecture provider contracts stable.
- [ ] Avoid mixing manifest-backed and build-graph-backed semantics without provenance distinctions.
- [ ] Keep build-graph-native providers separate from generic parsing/index approaches.

### Tests / acceptance
- [ ] Add provider-specific build-graph truth tests.
- [ ] Ensure provenance identifies build-graph-backed answers explicitly.
- [ ] Ensure no fallback guessing is presented as equivalent truth.

### Done when
- [ ] SuitCode can answer architecture questions from a real build graph in at least one additional ecosystem.

## Deferred / Not Now

- [ ] Graph DB / persisted graph as a product direction
- [ ] Vector search as a core identity
- [ ] Broad language coverage via generic AST indexing
- [ ] unittest authoritative structured discovery if it remains brittle
- [ ] richer provenance fields like command hashes or repo revision binding unless a real use case demands them
- [ ] full build-truth claims for ecosystems that are still coarse today
- [ ] generic shell-execution MCP tools

## README Direction

- [ ] README communicates what SuitCode does today.
- [ ] README names the near-term direction:
  - toolchain-backed truth
  - universal provenance
  - composed change analysis
  - deterministic execution surfaces
- [ ] README does not include an installation section yet.
- [ ] README makes clear that SuitCode is:
  - not a generic indexer
  - not a graph DB product
  - not a vector-search system
  - a deterministic repository intelligence engine backed by real tools

## Naming Guidance for Future MCP Functions

- [ ] Prefer task-explicit names over vague descriptive names.
- [ ] Prefer names like:
  - `analyze_change`
  - `describe_test_target`
  - `run_test_target`
  - `how_to_run_related_tests`
  - `describe_runner`
  - `run_runner`
  - `build_project`
  - `build_target`
- [ ] Avoid:
  - overlapping repo-wide names like `summary` vs `overview`
  - vague `describe_*` names when the task can be stated more directly
  - names that do not tell the agent what action or question they answer
