# MGA Hybrid Evaluation Protocol v1

This protocol defines the MyGamesAnywhere-first paper workflow that combines:
- live MGA sessions launched with explicit analytics metadata
- controlled MGA Codex evaluation tasks
- hybrid lab reports that merge both sources

## Run Types

### Live-study run
- launched with `python scripts/run_live_study.py`
- records explicit:
  - `analytics_run_id`
  - `task_id`
  - `task_kind`
  - `study_kind=live_session`
  - experiment metadata
- writes a launch manifest under:
  - `.suit/analytics/live-study/*.json`

### Controlled MGA run
- launched with `python scripts/run_codex_eval.py --tasks-file benchmarks/codex/tasks/mga_controlled_readonly.json`
- task metadata is embedded in the task file:
  - `tracked_repository_label`
  - `task_kind`
  - `study_kind=live_project_controlled`
- writes the normal Codex evaluation artifacts under:
  - `.suit/evaluation/codex/runs/<report_id>/...`

## Task Kinds

Use the following `SUITCODE_TASK_KIND` values:
- `discovery`
- `planning`
- `implementation`
- `bugfix`
- `validation`
- `review`

## Transcript Correlation

- live-session token estimates should use a Codex transcript when available
- transcript correlation is deterministic by:
  - workspace
  - transcript time window
  - optional `analytics_session_id`
  - optional `task_id`

## Exclusions

Do not delete raw events. Exclude via ignore metadata with a reason label:
- `parser_bug`
- `schema_bug`
- `user_aborted`
- `workspace_mismatch`
- `infrastructure_failure`
- `transcript_correlation_ambiguity`

## Clean Session Criteria

A session is clean enough for paper-facing slices when:
- transcript correlation is available or explicitly marked absent
- interrupted and unfinished calls are low
- degraded/fallback rates are low
- no known-bad parser/schema/infrastructure exclusion applies

## Reporting Cadence

- generate a live-study report after notable MGA live sessions
- generate a hybrid report after at least one new controlled MGA run or a meaningful live-session batch
- reassess paper-readiness only after several clean live MGA runs plus at least one stable controlled MGA slice
