# SuitCode Benchmark Protocol v1

## 1. Purpose

This protocol defines the first stable evaluation format for SuitCode.

It is intentionally narrow:
- Codex only
- stable bounded tasks first
- no stress tasks in headline results
- no cross-agent claims yet

The protocol compares:
- baseline native agent behavior
- baseline plus SuitCode

under a controlled, reproducible harness.

The current goal is to measure:
- workflow completion
- deterministic action correctness
- operational efficiency
- transcript-visible context efficiency
- provenance-aware actionability

## 1.1 Current protocol status

Protocol v1 is currently implemented for:
- Codex only
- downstream stable read-only headline A/B
- calibration A/B for orientation and truth coverage
- stable execution A/B evidence
- optional stress read-only reporting

The current canonical task files are:
- `benchmarks/codex/tasks/suitcode_v6_headline.json`
- `benchmarks/codex/tasks/suitcode_calibration.json`
- `benchmarks/codex/tasks/suitcode_execution_ab.json`
- `benchmarks/codex/tasks/suitcode_project_readonly.json`

The current v7 scaffold files are:
- `benchmarks/codex/tasks/suitcode_v7_headline.json`
- `benchmarks/codex/tasks/suitcode_v7_adoption_latency.json`
- `benchmarks/codex/comparisons/standout_codex_v7.json`

The current canonical report shape is the script-generated comparison bundle under:
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/`

## 2. Core Principles

### 2.1 Same agent, same task, same repo, same environment

Every A/B comparison must keep constant:
- model
- agent version
- OS
- repo revision
- benchmark prompt intent
- timeout budget
- working directory
- permissions and sandbox mode
- non-SuitCode tools available to the agent

Only SuitCode availability may differ between baseline and treatment.

### 2.2 Measured and estimated metrics stay separate

Reports must distinguish:
- measured metrics
- estimated metrics
- derived metrics

Estimated metrics must never be presented as billed-token truth unless the source is an authoritative vendor telemetry path.

### 2.3 Stable headline first

Headline claims come only from the bounded stable suite:
- deterministic
- low ambiguity
- reproducible
- infrastructure-light

Stress tasks may be reported separately, but must never silently alter headline metrics.

### 2.4 Task scoring is explicit

Every task must define:
- expected outcome
- pass criteria
- failure interpretation

Pass/fail is determined from explicit ground truth, not post-run narrative judgment.

## 3. Evaluation Conditions

### 3.1 Baseline

Baseline means the native agent without SuitCode.

The report must define baseline capabilities explicitly, including:
- filesystem exploration
- shell/search access
- native code navigation if available
- whether any custom MCP surfaces besides SuitCode are present

Current v1 baseline capability table:

| Capability | Baseline | Treatment |
| --- | --- | --- |
| Filesystem exploration | yes | yes |
| Native search / grep | yes | yes |
| Native code navigation | yes | yes |
| SuitCode MCP tools | no | yes |
| Deterministic test discovery | no | yes |
| Deterministic build target discovery | no | yes |
| Provenance-rich impact analysis | no | yes |

### 3.2 Treatment

Treatment means the same native agent with SuitCode enabled.

All non-SuitCode baseline capabilities remain available unless the report states otherwise.

## 4. Benchmark Families

Current headline families:
- change_analysis
- minimum_verified_change_set

Planned v7 headline families:
- bug_fix_navigation
- ci_debugging
- unsupported_action_reasoning

Calibration families:
- orientation
- truth_coverage

Execution families:
- test_execution
- build_execution

Future families may include:
- localization
- quality execution
- runner execution
- ownership reasoning
- dependency-path reasoning
- stress navigation

## 5. Headline vs Stress

### Headline suite

The headline suite must contain only stable bounded tasks.

Current headline:
- stable read-only
- bounded downstream tasks (`change_analysis` + `minimum_verified_change_set`)
- cold runs

Planned v7 headline:
- stable read-only
- one real-repo track plus one fixture track
- harder downstream tasks (`bug_fix_navigation`, `ci_debugging`, `unsupported_action_reasoning`)
- cold runs

### Stress suite

Stress tasks may be reported separately, but:
- must be labeled explicitly
- must not alter headline A/B conclusions
- must be treated as boundary or exploratory evidence

## 6. Task Schema

Every benchmark task has a machine-readable definition.

Current harness-required fields:
- `task_id`
- `repository_path`
- `task_family`
- `target_selector`
- `timeout_seconds`
- `expected_required_tools`
- `expected_high_value_tools`
- `output_schema_id`
- `prompt_template_id`

Optional protocol-facing metadata:
- `task_id`
- `task_family`
- `repository_path`
- `difficulty`
- `question`
- `expected_ground_truth_kind`
- `expected_success_criteria`
- `notes`

The current JSON schema is captured in:
- `docs/evaluation/task_schema.v1.json`

The current stable headline tasks are:
- `project-python-change-impact-headline`
- `project-python-minimum-verified-headline`
- `fixture-npm-change-impact-headline`
- `fixture-npm-minimum-verified-headline`

The current calibration tasks are:
- `project-python-orientation-calibration`
- `project-python-truth-coverage-calibration`
- `fixture-npm-orientation-calibration`
- `fixture-npm-truth-coverage-calibration`

The current stable execution tasks are:
- `fixture-python-test-execution`
- `fixture-npm-build-execution`

## 7. Repo Profile Metadata

Each evaluated repo must include:
- repository identifier
- language / ecosystem
- repository shape
- approximate file count
- build tool
- test tool
- quality tool(s)
- approximate component/package count
- approximate test count
- architecture truth source
- test truth source
- quality truth source

This prevents results from being mistaken for toy-repo-only outcomes.

Current v1 repositories:
- `.`
- `tests/test_repos/npm`
- `tests/test_repos/python`

## 8. Run Protocol

### 8.1 Session isolation

Each benchmark task runs in a fresh agent session unless explicitly marked as warm.

### 8.2 Cold vs warm

Protocol v1 distinguishes:
- cold
- warm

Current headline report uses:
- cold runs only

Warm-session benchmarking is reserved for a later protocol revision.

### 8.3 Environment capture

Each run must record:
- OS
- agent version
- model
- transport
- working directory
- sandbox / approval mode
- repo revision
- timestamp

## 9. Metrics

### 9.1 Measured metrics

Measured metrics are directly observed:
- task outcome
- wall-clock duration
- total agent turns when available
- total SuitCode MCP calls
- per-tool call counts
- selected target IDs
- execution success
- payload sizes in bytes/chars/items

Current headline-measured metrics:
- `task_success_rate`
- `answer_schema_success_rate`
- `avg_duration_ms`
- `required_tool_success_rate`
- `deterministic_action_success_rate`

### 9.2 Estimated metrics

Estimated metrics are explicitly labeled:
- transcript-estimated visible tokens
- estimated tokens before first SuitCode tool
- estimated tokens before first high-value SuitCode tool

Current headline-estimated metrics:
- `avg_transcript_tokens`
- `avg_tokens_before_first_suitcode_tool`
- `avg_tokens_before_first_high_value_tool`

### 9.3 Derived metrics

Derived metrics are computed from measured/estimated values:
- success-normalized token cost
- success-normalized time cost
- late-adoption labels
- inefficiency labels

Current headline-derived metrics:
- `success_normalized_token_cost`
- `success_normalized_time_cost`
- `late_suitcode_adoption`

## 10. Token Measurement Limitations

Transcript token estimates are based on visible content only:
- user prompts
- assistant responses
- tool calls
- tool outputs
- visible execution output

They do not include:
- hidden vendor prompts
- hidden reasoning
- cache internals
- undisclosed platform telemetry

These metrics are valid for relative comparison inside the same harness, but not as billed-token truth.

## 11. Failure Taxonomy

Every non-passing task must be assigned a failure class.

Current protocol taxonomy maps to:
- answer mismatch
- schema validation failed
- required tools missing
- argument mismatch
- required action not executed
- required action wrong target
- timeout
- cli error
- usage limit
- session artifact missing
- session correlation ambiguous
- unexpected exception

These are grouped into:
- answer correctness failures
- tool-use/scoring failures
- action correctness failures
- infrastructure failures

The canonical machine-readable taxonomy is:
- `docs/evaluation/failure_taxonomy.v1.json`

## 12. Required Report Sections

Every protocol-conformant report must include:
1. Evaluation scope and status
2. Agent metadata
3. Benchmark protocol
4. Baseline vs treatment definition
5. Task taxonomy
6. Repository profiles
7. Measured metrics
8. Estimated metrics
9. Derived metrics
10. Results summary
11. Failure analysis
12. Threats to validity
13. Repro commands

Current rendered report also includes:
- baseline failure analysis with question + expected vs actual answer
- suite inventory
- repository profile table
- measured/estimated/derived figure captions
- SVG figures with CSV sidecars

## 13. Threats to Validity

The report must explicitly discuss:
- Codex-only scope
- bounded task diversity
- fixture-heavy stable suite
- stress excluded from headline
- transcript-estimated tokens are not billed tokens
- baseline behavior is still Codex-specific
- current task families favor deterministic workflows

## 14. Freeze Rule

Protocol v1 is considered frozen when:
- baseline capability table is stable
- task schema is stable
- pass/fail scoring is deterministic
- failure taxonomy is implemented
- measured vs estimated separation is implemented
- at least one stable Codex A/B suite is complete

Only after that should additional agents or broader repo coverage be added.

Current state:
- the stable Codex headline A/B suite is complete
- the protocol/report shape is still being hardened before freeze
- no additional agents should be benchmarked until the report contract is locked

## 15. One-Sentence Summary

SuitCode Benchmark Protocol v1 evaluates whether adding SuitCode improves bounded deterministic repository workflows under controlled A/B conditions, using explicit ground truth, measured operational metrics, transcript-based context estimates, and provenance-aware scoring.
