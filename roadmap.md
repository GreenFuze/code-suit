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
- [x] Add a shared provenance model used across current public outputs:
  - architecture outputs
  - code outputs, including definition/reference locations
  - dependency outputs
  - related-test outputs
  - impact outputs
  - quality outputs where appropriate
- [x] Deliver Phase 1 incrementally so provenance can land in focused slices without widening risk.
- [x] Normalize core provenance concepts:
  - `confidence_mode`
  - `source_kind`
  - `source_tool`
  - short explanation / evidence summary
- [x] Attach provenance to:
  - dependencies
  - component context
  - file context
  - symbol context
  - impact outputs

### Refactor / design hardening
- [x] Remove duplicated provenance-like fields where they exist in ad hoc forms.
- [x] Ensure provenance is added in the correct layer:
  - provider-native evidence at provider/internal translation layer
  - cross-provider joins at intelligence/core layer
  - presentation-only shaping at MCP presenter layer
- [x] Review OO boundaries so provenance assembly is not duplicated across providers and MCP presenters.

### Tests / acceptance
- [x] Add tests for provenance consistency across:
  - authoritative outputs
  - derived outputs
  - heuristic fallback outputs
- [x] Add fail-fast tests for missing or contradictory provenance.
- [x] Add MCP tests to ensure provenance reaches the agent intact.

### Done when
- [x] Provenance is a shared typed concept.
- [x] Heuristic vs authoritative is not special-cased per feature anymore.
- [x] Every high-value answer class can explain where it came from.
- [x] Retrofit provenance onto raw architecture/code node outputs.
- [x] Normalize quality result provenance onto the shared provenance model.
- [x] Remove legacy test provenance fields once shared provenance becomes the sole contract.

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
- [x] Add a first-class `ChangeImpact` or `ChangeAnalysis` model.
- [x] Add a new MCP tool, likely `analyze_change`, or evolve `analyze_impact` into the north-star artifact if that keeps naming cleaner.
- [x] Include:
  - owner
  - primary component
  - dependent components
  - code references
  - related tests
  - related runners
  - quality providers / required gates
  - provenance per contributing category

### Refactor / design hardening
- [x] Avoid bloating `Repository` or one MCP service with the full composition logic.
- [x] Introduce dedicated orchestration objects where needed:
  - `ChangeImpactService`
- [x] Reuse existing context and reference services instead of duplicating logic.

### Tests / acceptance
- [x] Add representative file target coverage.
- [x] Add representative symbol target coverage.
- [x] Add representative owner target coverage.
- [x] Add explicit failure coverage for unresolved targets.
- [x] Add provenance coverage for each contributing evidence type.

### Done when
- [x] SuitCode exposes one high-level change artifact.
- [x] The output is factual, deterministic, and provenance-backed.
- [x] It does not pretend to be an execution plan yet.

## Phase 3: Action Model Foundation

### Goal
Introduce a typed, provider-backed action model so SuitCode can expose real executable surfaces instead of forcing agents to infer commands.

### Capability work
- [x] Add shared action/result types for deterministic actions such as:
  - test execution
  - runner execution
  - build execution
- [x] Model action concepts explicitly, for example:
  - action kind
  - provider
  - target ID
  - command / invocation
  - working directory
  - provenance
  - dry-run capability if applicable
- [x] Add a way to represent what actions are available for this repository, component, runner, or test target.
- [x] Add shared provenance to action outputs when action surfaces are introduced.

### Refactor / design hardening
- [x] Keep actions separate from pure intelligence outputs.
- [x] Do not leak raw shell/process concepts directly into MCP DTOs.
- [x] Introduce provider-native action abstractions instead of scattering command rendering through providers and MCP layers.
- [x] Enforce OO separation between:
  - discovery
  - context
  - execution rendering
  - execution results

### Tests / acceptance
- [x] Add action model validation tests.
- [x] Add fail-fast tests for unsupported targets.
- [x] Add provenance tests for action outputs.
- [x] Verify no generic shell-execution abstraction slips in.

### Done when
- [x] SuitCode has a typed foundation for deterministic actions.
- [x] Future test/build/run tools can be added without inventing ad hoc command payloads.

## Phase 4: Test Execution Guidance and Actions

### Goal
Turn related tests into a deterministic executable answer:
- what tests cover this
- how do I run only those
- optionally run them through SuitCode

### Capability work
- [x] Add exact run instructions for discovered test targets.
- [x] Add a test-target context model or tool, likely `describe_test_target` and/or `how_to_run_related_tests`.
- [x] Add a test action tool, likely `run_test_targets`.
- [x] For each supported framework, return:
  - exact runnable command pattern
  - whether the target is authoritative or heuristic
  - narrowed file/target scope when deterministic
- [x] Prefer existing test tools:
  - pytest
  - jest
  - future framework-specific tools when supported

### Refactor / design hardening
- [x] Separate:
  - test discovery
  - test relation logic
  - test execution rendering
  - test execution actions
- [x] Keep command construction framework-specific and OO, not scattered string building.
- [x] Avoid provider duplication by introducing shared test execution formatting helpers where appropriate.

### Tests / acceptance
- [x] Add pytest authoritative run guidance coverage.
- [x] Add jest authoritative run guidance coverage.
- [x] Add `run_test_targets` structured result tests.
- [x] Keep heuristic fallback cases clearly marked.
- [x] Add fail-fast tests for malformed or unsupported execution metadata.

### Done when
- [x] The agent can ask how to run only the relevant tests and get a deterministic answer.
- [x] The agent can invoke a real test target through a provider-backed action.
- [x] The result distinguishes authoritative from heuristic narrowing.

## Phase 5: Runner Context and Operational Actions

### Goal
Make runners first-class operational intelligence and executable surfaces rather than just listed nodes.

### Capability work
- [x] Add runner context, likely `describe_runner`.
- [x] Answer:
  - what this runner is
  - what component owns it
  - what files back it
  - what tests relate to it
  - how it is invoked
- [x] Add runner action tooling, likely `run_runner`.
- [x] Ensure actions expose exact invocations for:
  - npm scripts / workspace runners
  - python entry-point runners

### Refactor / design hardening
- [x] Centralize runner ownership and entrypoint resolution logic.
- [x] Avoid duplicate runner-context assembly between providers.
- [x] Keep architecture metadata and executable invocation semantics separated cleanly.
- [x] Ensure provider-native runner execution is modeled, not improvised per call site.

### Tests / acceptance
- [x] Add npm runner context and execution tests.
- [x] Add python runner context and execution tests.
- [x] Add fail-fast coverage for unknown runner IDs.
- [x] Verify no duplicated runner-resolution logic across providers.

### Done when
- [x] Runner questions no longer require combining multiple separate tools manually.
- [x] The agent can invoke known runner targets deterministically.

## Phase 6: Build and Project Actions

### Goal
Expose real build/project actions so the agent does not have to guess how to build or validate the project.

### Capability work
- [x] Add project/build action discovery, likely `list_project_actions` and/or provider-specific action discovery under a generic action model.
- [x] Add build action tooling, likely `build_project` and `build_target`.
- [x] Prefer existing build/system tools, for example:
  - npm workspace build scripts where authoritative
  - python project build tools only where there is a real deterministic build surface
  - future BSP/build-graph integrations where available
- [x] Return structured action results:
  - status
  - command used
  - working directory
  - affected target
  - provenance

### Refactor / design hardening
- [x] Keep build actions provider-backed.
- [x] Do not implement guessed best-effort build commands.
- [x] Separate:
  - action discovery
  - action execution
  - action result interpretation

### Tests / acceptance
- [x] Add deterministic build-action discovery tests.
- [x] Add provider-specific build action tests.
- [x] Add fail-fast tests for unsupported repositories or targets.
- [x] Verify no generic shell-wrapper behavior.

### Done when
- [x] The agent can ask how to build this project or target and get a deterministic answer.
- [x] The agent can invoke that build through SuitCode when supported.

## Phase 7: Generic LSP Backend Family

### Goal
Stop duplicating code-role plumbing per ecosystem by separating:
- ecosystem/build-system provider
- code backend mechanism

### Capability work
- [x] Introduce a generic LSP-backed code backend family or internal abstraction.
- [x] Move shared code-navigation logic out of ecosystem-specific providers.
- [x] Keep ecosystem-specific responsibility limited to:
  - server/tool resolution
  - file-type filtering
  - backend-specific initialization quirks
- [x] Explicitly prefer LSP before any custom code navigation implementation.

### Refactor / design hardening
- [x] Refactor current `python` and `npm` code-role logic onto the shared backend abstraction.
- [x] Remove duplicated symbol/definition/reference translation and filtering patterns where possible.
- [x] Keep the abstraction narrow enough to avoid overengineering.

### Tests / acceptance
- [x] Preserve behavior for:
  - `find_symbols`
  - `list_symbols_in_file`
  - `find_definition`
  - `find_references`
- [x] Keep provider-specific quirks covered.
- [x] Preserve fail-fast behavior for missing LSP/tool resolution.

### Done when
- [x] Adding a new LSP-backed language does not require copying the current provider code-role pattern.

## Phase 8: Deterministic Dependency Projections (No Maintained Graph)

### Goal
Answer graph-style architecture questions deterministically without maintaining a persisted repository graph.

### Capability work
- [x] Add a shared typed dependency-edge model (`source -> target`, scope, provenance).
- [x] Add provider bulk-edge extraction for npm and python.
- [x] Add one MCP bulk-edge tool (`list_component_dependency_edges`) to reduce per-component fanout.
- [x] Keep existing dependency/dependent tools, but derive them from the same edge projection path.
- [x] Keep outputs provenance-backed and deterministic.

### Refactor / design hardening
- [x] Keep architecture contracts stable while extending them with bulk-edge support.
- [x] Remove duplicated provider logic by centralizing dependency/dependent projection behavior in shared/base layers.
- [x] Enforce fail-fast for unknown component IDs and unresolved dependency targets.
- [x] Keep no-persisted-graph policy explicit; only ad hoc projections and in-memory caches are allowed.

### Tests / acceptance
- [x] Add provider tests for npm/python bulk edge extraction and consistency with per-component dependencies.
- [x] Add core tests for dependency-edge provenance validation.
- [x] Add MCP tests for bulk-edge tool registration, output shape, and fail-fast unknown component behavior.
- [x] Ensure dependency/dependent results stay consistent with bulk-edge projections.

### Done when
- [x] SuitCode answers graph-style dependency questions for npm/python without any persisted graph substrate.

## Phase 9: Intelligence Observability and Token-Savings Analytics

### Goal
Measure how much SuitCode helps agents, with a specific focus on token savings, tool adoption, and inefficient tool usage patterns.

### Capability work
- [ ] Add analytics event capture for all MCP tool calls.
- [ ] Persist analytics locally under repository `.suit/analytics/`.
- [ ] Track per-call metadata:
  - tool name
  - workspace/repository scope
  - full arguments
  - output excerpt metadata
  - status and error class
  - duration
  - payload size
- [ ] Add token estimation and a first-class KPI for estimated token savings.
- [ ] Mark savings estimates with confidence levels (`high`, `medium`, `low`) based on evidence quality.
- [ ] Detect and report underused or unused tools.
- [ ] Detect and report inefficient tool call patterns, including:
  - repeated duplicate calls
  - pagination thrash
  - broad exploratory calls where exact tools should have been used

### Refactor / design hardening
- [ ] Add one instrumentation layer around MCP tool registration, instead of per-tool logging code.
- [ ] Keep analytics logic in dedicated modules/services, not spread across MCP endpoints.
- [ ] Keep analytics schemas typed and versioned.
- [ ] Reuse shared validation/helpers so analytics additions do not duplicate existing logic.

### Tests / acceptance
- [ ] Add unit tests for analytics models and event validation.
- [ ] Add unit tests for token estimation and savings aggregation.
- [ ] Add unit tests for inefficient-call detectors.
- [ ] Add MCP integration tests proving all registered tools emit analytics events.
- [ ] Add fail-fast tests for invalid analytics config/storage/schema.

### Done when
- [ ] SuitCode can produce deterministic usage summaries per tool.
- [ ] SuitCode can produce estimated token-savings reports.
- [ ] SuitCode can report unused tools and top inefficient call patterns.

## Deferred / Not Now

- [ ] Graph DB / persisted graph as a product direction
- [ ] Vector search as a core identity
- [ ] Broad language coverage via generic AST indexing
- [ ] unittest authoritative structured discovery if it remains brittle
- [ ] richer provenance fields like command hashes or repo revision binding unless a real use case demands them
- [ ] full build-truth claims for ecosystems that are still coarse today
- [ ] generic shell-execution MCP tools
- [ ] external LLM/client token log correlation for high-fidelity savings validation

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
