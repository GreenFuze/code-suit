# Phase 3 Dogfooding Runbook

This runbook covers real usage collection after:
- Claude/Cursor passive analytics are available
- Go supports multi-module repo roots without `go.work`

Tracked repositories live in:
- [tracked_repositories.v1.json](tracked_repositories.v1.json)

## Tracked Repositories

- `suitcode`
  - `C:\src\github.com\GreenFuze\suit-code`
  - use this for daily product-on-product work
- `mygames-server`
  - `C:\src\github.com\GreenFuze\MyGamesAnywhere\server`
  - use this to validate real multi-module Go workflows

## Supported Agents

- Codex
  - live evaluation and passive analytics
- Claude Code
  - passive analytics
- Cursor
  - passive analytics

## Daily Workflow

Use SuitCode naturally in:
- Codex
- Claude Code
- Cursor

Prefer tasks that stress:
- ownership
- impact reasoning
- minimum verified change set
- unsupported action boundaries
- deterministic test/build selection

## Daily Quick Check

Run:

```powershell
python scripts/analyze_dogfooding.py --tracked-label suitcode
python scripts/analyze_dogfooding.py --tracked-label mygames-server
```

This writes:
- `.suit/dogfooding/<iso-utc>__<label>/summary.json`
- `.suit/dogfooding/<iso-utc>__<label>/summary.md`

## Weekly Review

Inspect:
- first SuitCode tool index
- first high-value SuitCode tool index
- transcript-estimated tokens before first SuitCode/high-value tool
- top SuitCode tools by agent
- MCP top tools and inefficiency mix
- unsupported repo/action patterns
- repeated late-adoption sessions

## What Counts As Useful Usage

Prefer sessions where the agent must:
- move from a vague task to a bounded validation plan
- choose between multiple plausible components
- explain why an action is unsupported
- decide what should run first

Avoid treating these as strong product evidence:
- sessions with no repository grounding need
- sessions dominated by plain editing with no repo reasoning
- sessions where the native artifact is incomplete or corrupted

## File Product Gaps vs Provider Bugs

File a provider bug when:
- ownership is wrong
- tests/build targets are wrong
- supported repos are marked unsupported
- actions or truth coverage contradict the underlying toolchain

File a product/workflow gap when:
- agents adopt SuitCode too late
- users repeatedly need a composed answer that requires manual tool chaining
- unsupported boundaries are technically correct but not actionable enough

## Two-Week Decision Rule

After 2 weeks, choose exactly one next workflow to add.

Prioritize the repeated winner among:
- CI failure triage
- unsupported-action alternative suggestion
- what-should-I-run-first
- another repeated pain that clearly dominates the summaries
