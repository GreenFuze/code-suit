# SEP-1686 Tasks Probe MCP

This folder contains a tiny standalone MCP server used only to test whether a client supports SEP-1686 task flows.

Server file:
- `taskstests/sep1686_task_probe_server.py`

## What it implements

- MCP `initialize` with advertised `capabilities.tasks`
- `tools/list`
- `tools/call`
- `tasks/get`
- `tasks/result`
- `tasks/list`
- `tasks/cancel`
- push notifications via `notifications/tasks/status`

## Tools

- `task_echo_required`
  - declares `"execution": { "taskSupport": "required" }`
  - expects `tools/call` to include `params.task`
  - creates a background task and returns a task handle
- `task_probe_capabilities`
  - returns the client capabilities observed at `initialize`
  - useful to confirm whether the client negotiated `capabilities.tasks`

## Run locally (stdio)

```powershell
python taskstests/sep1686_task_probe_server.py
```

## Add to Codex config (example)

Use your Codex MCP config and add a server entry similar to:

```toml
[mcp_servers.taskstests]
command = "python"
args = ["C:/src/github.com/GreenFuze/suit-code/taskstests/sep1686_task_probe_server.py"]
enabled = true
```

Adjust the absolute path to your workspace location.

## How to interpret results

1. Call `task_probe_capabilities`.
- If `capabilities.tasks` is missing, the client likely does not negotiate SEP-1686 tasks.

2. Call `task_echo_required`.
- If client supports task-augmented `tools/call`, it should create a task and return a task handle.
- If not, server returns an error that `params.task` is missing.

3. If a task is created, use:
- `tasks/get` to inspect status
- `tasks/result` to retrieve the terminal result

## Notes

- This is intentionally minimal and test-oriented, not production code.
- It does not persist tasks across process restarts.
