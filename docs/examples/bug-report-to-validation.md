# Bug Report To Validation

Scenario:
- A bug report points at `src/suitcode/mcp/service.py`
- You want the agent to stop wandering and narrow to the right debugging surface and validation plan first

## Prompt

```text
A bug report points at src/suitcode/mcp/service.py.
What owns it, what should I inspect first, and what exact validation set should run before I trust a fix?
```

## What SuitCode surfaces

Use the deterministic path:
1. `inspect_repository_support`
2. `open_workspace`
3. `analyze_change` or `analyze_impact`
4. `get_minimum_verified_change_set`
5. `describe_test_target` or `describe_build_target` if execution detail is needed

## What the agent gets back

The result is grounded in toolchain truth rather than broad search:
- owning component or owner id
- dependency frontier that defines the debugging surface
- related tests and quality gates
- exact deterministic validation targets
- explicit unsupported boundaries when an action kind is unavailable

## Why this is better than blind exploration

Without SuitCode, the agent has to guess:
- which component really owns the file
- whether related tests are direct or incidental
- what the minimum validation path is
- whether a runner/build/test action is actually supported

With SuitCode, the agent can move from a vague bug report to a bounded validation plan:
- inspect the right surface first
- run only the deterministic validation set
- stop before inventing unsupported targets

## Minimal example flow

```text
User: A bug report points at src/suitcode/mcp/service.py. What should I inspect first?
Agent: opens the workspace and asks for evidence-backed change analysis
SuitCode: returns owner, related tests, and dependency frontier
User: What exact validation set should run before a fix is trusted?
Agent: asks for the minimum verified change set
SuitCode: returns the exact deterministic test/build/runner/quality set available for that change
```

This is the workflow SuitCode is optimized for: narrow first, validate exactly, and avoid exploratory thrash.
