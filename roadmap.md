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
- [x] Add analytics event capture for all MCP tool calls.
- [x] Persist analytics locally under repository `.suit/analytics/`.
- [x] Track per-call metadata:
  - tool name
  - workspace/repository scope
  - full arguments
  - output excerpt metadata
  - status and error class
  - duration
  - payload size
- [x] Add token estimation and a first-class KPI for estimated token savings.
- [x] Mark savings estimates with confidence levels (`high`, `medium`, `low`) based on evidence quality.
- [x] Detect and report underused or unused tools.
- [x] Detect and report inefficient tool call patterns, including:
  - repeated duplicate calls
  - pagination thrash
  - broad exploratory calls where exact tools should have been used
- [x] Add side script analytics analyzer for usage/savings/inefficiency reporting.
- [x] Add benchmark harness scaffold and benchmark report output contract.

### Refactor / design hardening
- [x] Add one instrumentation layer around MCP tool registration, instead of per-tool logging code.
- [x] Keep analytics logic in dedicated modules/services, not spread across MCP endpoints.
- [x] Keep analytics schemas typed and versioned.
- [x] Reuse shared validation/helpers so analytics additions do not duplicate existing logic.

### Tests / acceptance
- [x] Add unit tests for analytics models and event validation.
- [x] Add unit tests for token estimation and savings aggregation.
- [x] Add unit tests for inefficient-call detectors.
- [x] Add MCP integration tests proving all registered tools emit analytics events.
- [x] Add fail-fast tests for invalid analytics config/storage/schema.

### Done when
- [x] SuitCode can produce deterministic usage summaries per tool.
- [x] SuitCode can produce estimated token-savings reports.
- [x] SuitCode can report unused tools and top inefficient call patterns.

## Phase 10: Refactor Hardening (Low-Risk Dedup)

### Goal
Reduce duplication and keep object boundaries clean without changing public MCP contracts.

### Capability work
- [x] Keep behavior stable while deduplicating repeated provider internals.
- [x] Keep fail-fast behavior and deterministic action semantics unchanged.

### Refactor / design hardening
- [x] Extract shared deterministic test-target runtime flow for providers.
- [x] Extract shared quality file pipeline for path normalization, hash snapshots, and entity snapshots.
- [x] Extract shared LSP symbol-service base used by npm/python symbol services.
- [x] Extract MCP tool instrumentation into a dedicated module.

### Tests / acceptance
- [x] Add focused unit tests for shared test-target runtime behavior.
- [x] Add focused unit tests for shared quality file pipeline behavior.
- [x] Add focused tests for MCP instrumentation helper behavior.
- [x] Run full suite and keep all tests passing after refactor.

### Done when
- [x] Duplication in the targeted hotspots is reduced.
- [x] Public contracts remain stable.
- [x] Refactor keeps fail-fast and deterministic guarantees intact.

## Phase 11: Early Evaluation Telemetry

### Goal
Capture enough telemetry early to evaluate how agents use SuitCode while other roadmap phases are still being built, without blocking on full public benchmark infrastructure or vendor-perfect token reporting.

### Capability work
- [x] Add benchmark/run correlation fields across analytics and benchmark artifacts:
  - benchmark run ID
  - benchmark task ID
  - agent/session ID
  - repo/task scope
- [x] Add transcript/artifact capture hooks for native-agent runs, even before full transcript-token accounting is complete.
- [x] Add per-run metrics beyond MCP call counts:
  - total turns
  - first high-value SuitCode tool used
  - deterministic action success
  - authoritative / derived / heuristic mix
- [x] Add native artifact archival hooks where practical:
  - Codex session artifact path
  - Claude telemetry/log reference
  - Cursor run metadata reference
- [x] Add a benchmark/eval summary output that can answer:
  - was SuitCode used?
  - was it used early?
  - did it lead to deterministic action execution?
  - what trust mix did the run produce?

### Refactor / design hardening
- [x] Keep this telemetry slice strictly as enabling infrastructure, not a full benchmark product.
- [x] Reuse existing analytics models/services where semantics align; create benchmark-specific models only where necessary.
- [x] Keep vendor-specific capture behind adapters so core analytics stays vendor-neutral.
- [x] Fail fast when telemetry capture is explicitly requested but the required artifact path/source is unavailable.

### Tests / acceptance
- [x] Add tests for benchmark/task/session correlation fields.
- [x] Add tests for transcript/artifact path capture.
- [x] Add tests for per-run derived metrics such as first high-value tool used and action-success summaries.
- [x] Add fail-fast coverage for missing configured artifact sources.

### Done when
- [x] Future roadmap phases can be measured with per-run telemetry instead of only aggregate MCP usage.
- [x] SuitCode can evaluate agent behavior during feature development without waiting for full public benchmark infrastructure.

## Phase 12: Proof-Carrying Change Graph

### Goal
Upgrade `analyze_change` from a provenance-backed summary into a proof-carrying change graph where every returned relationship and recommendation can explain exactly why it exists.

### Capability work
- [x] Extend `ChangeImpact` so each major returned category carries explicit evidence edges, not only summarized provenance:
  - owner resolution edges
  - ownership-to-component edges
  - symbol/reference edges
  - component dependency edges
  - related-test inclusion edges
  - runner inclusion edges
  - quality-gate applicability edges
- [x] Add a typed edge model, for example:
  - `ChangeEvidenceEdge`
  - `source_node_id`
  - `target_node_id`
  - `edge_kind`
  - `reason`
  - `provenance`
- [x] Add optional graph-style previews to `analyze_change` output:
  - evidence edge count
  - evidence edges preview
  - grouped edges by category
- [x] Keep current summary fields intact so existing consumers do not lose the high-level artifact.

### Refactor / design hardening
- [x] Keep proof-carrying edge assembly in dedicated orchestration logic, not inside MCP presenters.
- [x] Avoid duplicating dependency/test/reference reasoning across:
  - `ContextService`
  - `ImpactService`
  - `ChangeImpactService`
- [x] Introduce one focused internal object to assemble proof edges:
  - `ChangeEvidenceAssembler`
- [x] Ensure edge generation reuses existing provenance-bearing outputs instead of inventing parallel evidence models.

### Tests / acceptance
- [x] Add tests proving each edge category is populated from current evidence sources.
- [x] Add fail-fast tests for unresolved evidence links and contradictory edge assembly.
- [x] Add MCP tests to ensure proof edges reach the final tool output.
- [x] Add acceptance coverage for:
  - file target
  - symbol target
  - owner target

### Done when
- [x] `analyze_change` can explain each inclusion with explicit edge-level evidence.
- [x] SuitCode can distinguish summary provenance from proof graph evidence.
- [x] Existing high-level `analyze_change` consumers remain compatible.

## Phase 13: Minimum Verified Change Set

### Goal
Return the smallest deterministic validation frontier required to trust a change for a given file, symbol, or owner.

### Capability work
- [x] Add a first-class artifact:
  - `MinimumVerifiedChangeSet`
- [x] Add a new MCP tool:
  - `get_minimum_verified_change_set`
- [x] The artifact must include:
  - target owner / primary component
  - exact related tests
  - exact build targets
  - exact runners
  - quality gates
  - exclusion reasoning where applicable
  - proof edges / provenance per included item
- [x] Distinguish:
  - authoritative inclusion
  - derived inclusion
  - heuristic fallback inclusion
- [x] Add “why minimal” semantics:
  - deduplicated targets
  - removed supersets
  - no unrelated validation surfaces

### Refactor / design hardening
- [x] Do not overload `analyze_change` with minimum-validation-set logic.
- [x] Introduce a dedicated service:
  - `MinimumVerifiedChangeSetService`
- [x] Reuse:
  - existing repository descriptors and provider-backed discovery surfaces
  - action discovery
  - test/build/runner descriptors
  - quality applicability logic
- [x] Keep minimization logic explicit and testable; avoid ad hoc filtering inside presenters.

### Tests / acceptance
- [x] Add tests proving the returned set is:
  - deterministic
  - deduplicated
  - smaller or equal to the full change frontier
- [x] Add fail-fast tests for targets with no validation surfaces.
- [x] Add provider-specific coverage for:
  - python
  - npm
- [x] Add MCP acceptance coverage for exact target selection and proof visibility.

### Done when
- [x] SuitCode can answer “what is the minimum exact set I must validate for this change?”
- [x] The answer is not a guess and includes evidence for every returned target.

## Phase 14: Truth Coverage Map

### Goal
Expose how much of SuitCode’s understanding is authoritative, derived, or heuristic for a repository and for individual answers.

### Capability work
- [x] Add a typed coverage model:
  - `TruthCoverageSummary`
  - `TruthCoverageByDomain`
- [x] Coverage domains should include at minimum:
  - architecture
  - code
  - tests
  - quality
  - actions
- [x] For each domain, report:
  - total entities
  - authoritative count
  - derived count
  - heuristic count
  - execution availability where relevant
  - degraded / unavailable reason where relevant
- [x] Add one MCP tool:
  - `get_truth_coverage`
- [x] Add optional truth-coverage attachment to:
  - `repository_summary`
  - `analyze_change`
  - benchmark reports

### Refactor / design hardening
- [x] Compute truth coverage from existing provenance, not from duplicated role-specific counters.
- [x] Centralize coverage classification logic in one internal service:
  - `TruthCoverageService`
- [x] Avoid mixing repository-wide coverage and artifact-local coverage into one object unless clearly separated.

### Tests / acceptance
- [x] Add tests for coverage classification across:
  - authoritative
  - derived
  - heuristic
  - unavailable
- [x] Add provider-specific tests for current python/npm realities.
- [x] Add MCP tests for coverage tool output shape and consistency.

### Done when
- [x] SuitCode can explicitly report where it is authoritative and where it is partially blind.
- [x] Benchmark reports can reference trust coverage instead of only success metrics.

## Phase 15: Native-Agent Evaluation Harness

### Goal
Evaluate SuitCode under real native agents (Codex CLI, Claude Code, Cursor CLI/headless) without requiring stable vendor token APIs.

Status note:
- [x] Codex passive-ingestion telemetry is implemented:
  - rollout discovery from `~/.codex/sessions`
  - repository/session filtering
  - SuitCode MCP usage detection
  - server-local analytics correlation
- [x] Codex harness-owned execution is implemented:
  - `codex exec` task execution
  - fixed prompt/control automation
  - structured scoring and stored reports
  - smoke evaluation task file for fast sanity checks
- [x] Codex smoke stabilization is implemented for the current supported ecosystems:
  - `python` truth-coverage smoke passes
  - `npm` truth-coverage smoke passes
  - required-tool traces are attached to evaluation results and analyzers
- [x] Codex read-only stabilization is implemented for the current supported ecosystems:
  - stable fixture-based read-only suite (`suitcode_readonly.json`) passes end to end
  - `orientation`, `change_analysis`, `minimum_verified_change_set`, and `truth_coverage` are covered for both `python` and `npm`
  - live-project read-only tasks are split into a separate stress suite (`suitcode_project_readonly.json`)
- [x] Codex execution-task stabilization is implemented for the current stable fixture suite:
  - stable execution suite (`suitcode_execution.json`) passes end to end
  - `python` test execution and `npm` build execution both pass with required-tool traces
  - subprocess-driven actions and discovery no longer inherit interactive stdin from the stdio MCP server
- [ ] Remaining native-agent expansion work:
  - launching/evaluating Claude and Cursor under the same contract
  - unified benchmark execution across Codex/Claude/Cursor

### Capability work
- [ ] Add a benchmark runner layer for native agents, distinct from internal deterministic workflow benchmarks.
- [ ] Introduce a typed run model:
  - `NativeAgentBenchmarkRun`
  - `NativeAgentTaskResult`
- [ ] Add adapter families for:
  - `codex_cli`
  - `claude_code`
  - `cursor_cli`
- [ ] Each adapter must support:
  - fresh session per task
  - fixed prompt injection
  - MCP availability configuration
  - run budget / timeout
  - result capture
- [ ] Add run outputs:
  - success / failure / error
  - wall-clock duration
  - turn count
  - SuitCode MCP tool calls
  - first high-value tool used
  - deterministic action success
  - transcript artifact path
  - native token metrics when available
  - provenance / truth coverage summary when available

### Refactor / design hardening
- [ ] Keep vendor-specific automation isolated behind adapter classes.
- [ ] Do not mix native-agent execution with core MCP benchmark harness classes.
- [ ] Introduce a shared benchmark run contract so all agents emit comparable result objects.
- [ ] Fail fast when a required native-agent capability is unavailable on the current machine.

### Tests / acceptance
- [ ] Add dry-run/adapter contract tests for each native-agent adapter.
- [ ] Add fixture-based tests for transcript/result parsing.
- [ ] Add fail-fast tests for:
  - missing agent executable
  - unsupported headless mode
  - malformed transcript output
  - missing token export path when configured as required

### Done when
- [ ] SuitCode can run the same task suite through real native agents.
- [ ] Benchmark outputs are comparable even when token observability differs by vendor.

## Phase 16: Transcript-Based Token Accounting

### Goal
Provide a cross-agent token accounting layer based on captured transcripts, independent of vendor billing exports.

Status note:
- [x] Codex/OpenAI passive-ingestion transcript token accounting is implemented.
- [ ] Claude/Cursor transcript token accounting and native-agent benchmark integration remain.

### Capability work
- [x] Add transcript capture schema including:
  - user prompt
  - assistant messages
  - MCP tool calls
  - MCP tool outputs
  - terminal/tool output shown to the agent
  - final answer
- [x] Add transcript token accounting service:
  - `TranscriptTokenEstimator`
- [x] Report:
  - input transcript tokens
  - tool-output transcript tokens
  - total transcript tokens
  - tokens to first decisive high-value tool
  - tokens to success
- [x] Keep this separate from existing heuristic “tokens saved” analytics.
- [ ] Where native token exports exist, store both:
  - native token metrics
  - transcript token estimate

### Refactor / design hardening
- [x] Do not present transcript-token estimates as billing truth.
- [x] Introduce an explicit metric-kind field:
  - `native_reported`
  - `transcript_estimated`
  - `heuristic_saved`
- [x] Reuse current analytics schemas only where the semantics are actually compatible; otherwise create a benchmark-specific metric schema.

### Tests / acceptance
- [x] Add unit tests for transcript token accounting over representative benchmark traces.
- [ ] Add tests for missing or partial transcript segments.
- [x] Add tests ensuring native-reported and estimated metrics are not conflated.

### Done when
- [ ] Every native-agent benchmark run has a token metric even if the agent does not expose one natively.
- [ ] Public evaluation claims can rely on transcript estimates as the common denominator.

## Phase 17: Public Comparison Baselines and Benchmark Suite

### Goal
Make SuitCode’s evaluation story externally defensible with baseline comparisons and standardized benchmark task families.

### Capability work
- [ ] Split benchmark tasks into families:
  - tool-use correctness
  - repository-context quality
  - end-to-end issue resolution
  - SuitCode-native deterministic workflows
- [ ] Add baseline modes:
  - filesystem/search-only
  - LSP-first
  - search-first
  - structure/graph-first where practical
- [ ] Define per-task metrics:
  - task success
  - turns to success
  - time to success
  - SuitCode tool calls
  - high-value tool correctness
  - argument correctness where measurable
  - action execution success
  - authoritative evidence rate
  - transcript tokens to success
- [ ] Add benchmark result grouping by:
  - agent
  - repo
  - task family
  - cold start vs warm state
  - baseline vs treatment

### Refactor / design hardening
- [ ] Keep benchmark dataset definitions separate from runner logic.
- [ ] Keep baseline configuration explicit and reproducible.
- [ ] Introduce one result aggregation/reporting layer that can emit:
  - machine-readable JSON
  - human-readable markdown summary

### Tests / acceptance
- [ ] Add validation for benchmark task schemas and baseline configs.
- [ ] Add acceptance tests for cold vs warm state accounting.
- [ ] Add report-generation tests ensuring all published metrics are reproducible from stored artifacts.

### Done when
- [ ] SuitCode can run reproducible A/B benchmark families under consistent harness settings.
- [ ] Public comparison reports can be generated without manual spreadsheet stitching.

## Phase 18: Native Token Telemetry Integrations

### Goal
Add optional native token telemetry collection where agents expose it, without making benchmark validity depend on vendor support.

### Capability work
- [ ] Add optional Claude Code telemetry ingestion:
  - OTel metrics/logs
  - token counters
  - request/tool activity
- [ ] Add Codex session artifact ingestion:
  - rollout/session JSONL archival
  - optional extraction of usage-like fields when version-validated
- [ ] Add Cursor usage ingestion:
  - dashboard/API batch accounting integration where practical
- [ ] Join native token telemetry to benchmark runs by:
  - session ID
  - task ID
  - timestamp window

### Refactor / design hardening
- [ ] Treat native telemetry as optional enrichments, not required benchmark dependencies.
- [ ] Add explicit stability classification for vendor integrations:
  - documented stable
  - version-dependent
  - experimental
- [ ] Keep telemetry correlation logic outside core analytics used by SuitCode MCP itself.

### Tests / acceptance
- [ ] Add parser tests for each supported telemetry source.
- [ ] Add fail-fast tests for incompatible or missing telemetry configuration.
- [ ] Add explicit warnings for unstable vendor-derived usage fields.

### Done when
- [ ] SuitCode can enrich benchmark runs with native token telemetry where available.
- [ ] Lack of native token telemetry does not block evaluation.

## Deferred / Not Now

- [ ] Graph DB / persisted graph as a product direction
- [ ] Vector search as a core identity
- [ ] Broad language coverage via generic AST indexing
- [ ] unittest authoritative structured discovery if it remains brittle
- [ ] richer provenance fields like command hashes or repo revision binding unless a real use case demands them
- [ ] full build-truth claims for ecosystems that are still coarse today
- [ ] generic shell-execution MCP tools
- [ ] cross-vendor billing-accurate token parity as a strict requirement
- [ ] public benchmark claims based solely on heuristic token savings
- [ ] vendor-specific hidden-prompt accounting unless the vendor exposes it reliably

## README Direction

- [x] README communicates what SuitCode does today.
- [x] README names the near-term direction:
  - toolchain-backed truth
  - universal provenance
  - composed change analysis
  - deterministic execution surfaces
- [x] README does not include an installation section yet.
- [x] README makes clear that SuitCode is:
  - not a generic indexer
  - not a graph DB product
  - not a vector-search system
  - a deterministic repository intelligence engine backed by real tools
- [ ] README eventually includes:
  - proof-carrying change analysis
  - minimum verified change set
  - truth coverage reporting
  - public benchmark methodology
  - transcript-estimated vs native-reported token metrics distinction

## Naming Guidance for Future MCP Functions

- [ ] Prefer task-explicit names over vague descriptive names.
- [ ] Prefer names like:
  - `analyze_change`
  - `get_minimum_verified_change_set`
  - `get_truth_coverage`
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

