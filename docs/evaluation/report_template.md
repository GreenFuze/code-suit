# Evaluation Report Template

Use this template for the canonical script-generated comparison report. It is protocol-facing, not a free-form narrative.

## 1. Evaluation Scope and Status

- agent scope: `codex_only`
- protocol status: `initial_stable_protocol`
- headline suite: stable read-only A/B only
- stable execution status: SuitCode-only deterministic action evidence
- stress status: separately reported and never merged into the headline A/B
- claim scope: bounded deterministic workflows only
- token accounting mode: `transcript_estimated_visible_content_only`

## 2. Agent Metadata

Required fields:
- agent family
- cli name and version
- model
- provider
- OS
- working directory
- sandbox mode
- approval / bypass mode
- transport
- git commit
- git branch
- git remote
- report generation time
- exact command prefix and config overrides per arm

## 3. Baseline vs Treatment Definition

The report must include a capability table, not prose only.

| Capability | Baseline | Treatment |
| --- | --- | --- |
| Filesystem exploration | yes | yes |
| Native search / grep | yes | yes |
| Native code navigation | yes | yes |
| SuitCode MCP tools | no | yes |
| Deterministic test discovery | no | yes |
| Deterministic build target discovery | no | yes |
| Provenance-rich impact analysis | no | yes |

## 4. Repository Profiles

| Repository | Ecosystem | Components | Tests | Build tool | Architecture basis | Test basis | Quality basis | Notes |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |

## 5. Benchmark Protocol

### Conditions
- baseline condition
- treatment condition
- session policy
- timeout policy
- repo state policy
- cold vs warm policy

### Task Taxonomy

| Task | Taxonomy | Difficulty | Temperature | Question | Ground truth | Success criteria | Selector |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Measured Metrics
- task success / fail / error
- wall-clock duration
- required tool usage
- deterministic action execution success
- payload sizes / counts when reported

### Estimated Metrics
- transcript-estimated tokens
- transcript-estimated tokens before first SuitCode tool
- transcript-estimated tokens before first high-value SuitCode tool

### Derived Metrics
- success-normalized token cost
- success-normalized time cost
- late-adoption labels
- other explicitly labeled derived metrics only

## 6. Results

### Headline A/B
- stable read-only suite only
- measured and estimated metrics must be visually separated
- headline interpretation must state what the result does and does not claim

### Stable Execution
- SuitCode-only section
- must state why it is excluded from the headline A/B
- must report deterministic action correctness explicitly

### Stress
- optional
- must be clearly marked as non-headline
- must never change headline totals

## 7. Failure Analysis

### Failure Taxonomy
- infrastructure
- tool-use / scoring
- answer correctness
- action correctness

Each failure kind should state:
- what it means
- whether it counts as a benchmark failure
- whether it is retryable

### Task-Level Failures
- question
- expected answer
- actual answer
- field-level expected vs actual differences
- failure kind
- plain-language explanation
- artifact paths

## 8. Threats to Validity

Required subcategories:
- internal validity
- external validity
- measurement validity
- product-scope validity

## 9. Artifact Map

Must include:
- report json
- report markdown
- figures directory
- figure CSV sidecars directory
- underlying run ids
- task artifact directory roots

## 10. Repro Commands

Must include exact commands for:
- run
- analyze
- refresh from existing artifacts when supported
