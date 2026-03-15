# Evaluation Guide

This document explains how to run SuitCode evaluation workflows and how to interpret the generated artifacts.

External review policy:
- the script-generated `comparison.md` is the only reviewer-facing markdown artifact
- the files under `docs/evaluation/` are internal protocol/spec inputs
- reviewers should not need to read multiple markdown files to understand one benchmark result

## Evaluation Protocol

Current paper-oriented reports are protocol-first. They define:
- baseline vs treatment conditions
- task taxonomy
- ground-truth kind per task
- success criteria per task
- repository profiles
- measured vs estimated vs derived metrics

Canonical protocol documents:
- `docs/evaluation/benchmark_protocol_v1.md`
- `docs/evaluation/task_schema.v1.json`
- `docs/evaluation/failure_taxonomy.v1.json`
- `docs/evaluation/baseline_capabilities.v1.json`
- `docs/evaluation/repo_profile.template.json`
- `docs/evaluation/report_template.md`

Current default protocol status:
- Codex only
- stable benchmark shape
- headline A/B limited to the bounded downstream stable read-only suite
- calibration suite reports orientation and truth-coverage separately
- stable execution reported as A/B deterministic action evidence
- stress read-only reported separately when included

## Scope

Current live evaluation support:
- Codex CLI

Current schema-level support reserved for future work:
- Claude
- Cursor

The report schema already records agent metadata in a way that is intended to be reusable for those agents when live harnesses are added.

## Output Locations

Evaluation runs:
- `.suit/evaluation/codex/runs/<report_id>/report.json`
- `.suit/evaluation/codex/runs/<report_id>/tasks/<task_id>/metadata.json`

Comparison runs:
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/comparison.json`
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/comparison.md`
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/inputs.json`
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/figures/*.svg`
- `.suit/evaluation/codex/comparisons/<iso-utc>__<comparison_id>/figures/data/*.csv`

Where:
- `<comparison_id>` is the logical report id, for example `codex-comparison-...`
- `<iso-utc>` is the report generation time in Windows-safe ISO form, for example `2026-03-10T09-57-58Z`

## Paper-Grade Metadata

New evaluation reports include agent metadata. For Codex runs, this captures:
- agent family
- CLI name
- CLI version when available from the rollout artifact
- model name when available from the rollout artifact
- model provider
- host OS
- working directory
- command prefix
- config profile
- config overrides
- full-auto vs manual sandbox mode
- sandbox mode
- approvals/sandbox bypass flag
- whether SuitCode was enabled
- MCP transport
- git commit hash
- git branch
- git repository URL

Per-task results also capture:
- session id
- rollout artifact path
- output-last-message path
- exact invocation command
- required-tool traces

## Stable Suites

Fast smoke suite:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_smoke.json --timeout-seconds 180
python scripts/analyze_codex_eval.py --latest
```

Stable v6 headline suite:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_v6_headline.json
python scripts/analyze_codex_eval.py --latest
```

Planned v7 headline suite scaffold:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_v7_headline.json --timeout-seconds 300
python scripts/analyze_codex_eval.py --latest
```

Calibration suite:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_calibration.json
python scripts/analyze_codex_eval.py --latest
```

Stable execution A/B suite:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_execution_ab.json --timeout-seconds 300
python scripts/analyze_codex_eval.py --latest
```

Live-project stress suite:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_project_readonly.json
python scripts/analyze_codex_eval.py --latest
```

## Standout Comparison

Headline comparison without stress:
```powershell
python scripts/run_codex_comparison.py --skip-stress
python scripts/analyze_codex_comparison.py --latest
```

Full comparison:
```powershell
python scripts/run_codex_comparison.py
python scripts/analyze_codex_comparison.py --latest
```

V7 comparison scaffold:
```powershell
python scripts/run_codex_comparison.py --spec-file benchmarks/codex/comparisons/standout_codex_v7.json
python scripts/analyze_codex_comparison.py --latest
```

The comparison bundle contains:
- headline downstream A/B
- calibration A/B section
- stable execution A/B section
- optional stress read-only SuitCode-only section
- generated figures embedded into `comparison.md`
- per-figure CSV sidecars under `figures/data/`
- methodology
- limitations
- repro commands

Headline A/B task file:
- `benchmarks/codex/tasks/suitcode_v6_headline.json`
- `benchmarks/codex/tasks/suitcode_v7_headline.json` (scaffold for harder downstream tasks)

The headline suite is intentionally bounded to downstream developer tasks:
- `change_analysis`
- `minimum_verified_change_set`

Calibration task file:
- `benchmarks/codex/tasks/suitcode_calibration.json`

Adoption-latency experiment:
```powershell
python scripts/run_codex_adoption_experiment.py --tasks-file benchmarks/codex/tasks/suitcode_v7_adoption_latency.json --timeout-seconds 300
```

The adoption experiment compares:
- default SuitCode task prompting
- the same SuitCode task prompting with `--auto-orientation-hint`

It writes artifacts under:
- `.suit/evaluation/codex/adoption/<iso-utc>__<experiment_id>/summary.json`
- `.suit/evaluation/codex/adoption/<iso-utc>__<experiment_id>/summary.md`

## JSON Output

Per-run evaluation report:
```powershell
python scripts/analyze_codex_eval.py --report-id <report_id> --json
```

Comparison report:
```powershell
python scripts/analyze_codex_comparison.py --report-id <comparison_id> --json
```

These JSON artifacts are the preferred input for paper tables and downstream analysis.

## Figures

Comparison reports generate figures automatically through the reporting pipeline. The markdown report embeds SVG figures using relative paths and keeps the plotted values in CSV sidecars for reproducibility.

Main figures:
- headline A/B outcomes
- headline A/B cost comparison
- stable execution outcome matrix

Supporting figures:
- task-level duration and token comparison
- failure taxonomy by suite and arm
- transcript token composition
- passive SuitCode adoption distribution when passive analytics are available

Use the SVG files for human-readable report review and paper drafting. Use the CSV sidecars for exact values, appendix tables, and re-plotting if needed.

## Non-Full-Auto Execution

When needed, direct `run_codex_eval.py` can be run without `--full-auto`:
```powershell
python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/suitcode_execution_ab.json --no-full-auto --sandbox danger-full-access --bypass-approvals-and-sandbox
```

The comparison harness already selects the Codex execution mode it needs and records that choice in report methodology and metadata.

## What Invalidates a Run

A run should not be used as a product-quality result if:
- Codex hit a usage limit
- session artifact correlation failed
- the final answer file is missing or empty because the agent never completed
- the report shows infrastructure failure kinds instead of task-quality failures

The comparison harness now fails fast on Codex usage-limit failures instead of generating a misleading standout report.

## Token Metrics

Current token numbers are:
- `transcript_estimated`

They are computed from visible Codex rollout content only. They are valid for relative comparison inside this harness, but they are not billing-accurate vendor totals.

The report separates metrics into:
- `measured`: direct run outcomes such as success rate, duration, action execution success
- `estimated`: transcript-estimated token counts
- `derived`: normalized or interpretive metrics such as success-normalized cost and late-adoption labels

## Recommended Reporting Discipline

For an academic paper, retain:
- the JSON report
- the markdown comparison report
- the comparison inputs file
- the rollout artifact references
- the git commit hash
- the exact CLI command used
- the protocol docs under `docs/evaluation/`

Do not quote a comparison as valid if the run failed due to:
- `usage_limit`
- `cli_error`
- `session_artifact_missing`
- `session_correlation_ambiguous`

Those are infrastructure or account-state failures, not repository-intelligence outcomes.
