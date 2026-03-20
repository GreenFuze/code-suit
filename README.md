# SuitCode

**Your agent can search the repo. SuitCode asks the toolchain.**

**Know what breaks, what to run, and why.**

Stop guessing and exploring blindly. SuitCode turns repo/toolchain signals into deterministic actions.

SuitCode is an MCP server for repository intelligence that reads the same surfaces your build, test, quality, and language tooling already define. Instead of giving your agent another repo map or another search index, it gives grounded answers like ownership, impact, minimum validation sets, deterministic targets, and explicit unsupported boundaries.

## Why It Is Different

- Search tells the agent where text appears. SuitCode asks the actual toolchain what owns the file, what depends on it, and what should run.
- Repo maps summarize structure. SuitCode returns deterministic actions and provenance-rich evidence.
- RAG and index layers guess from documents. SuitCode tells the agent when something is unsupported instead of inventing a target.
- Generic shell flows leave the agent to compose commands. SuitCode exposes exact test, build, and runner actions where the provider can prove them.

## Quick Proof

- Stable downstream A/B: SuitCode `5/5` vs baseline `2/5`
- Median turns per stable headline task: SuitCode `3` vs baseline `16`
- Stable execution A/B: SuitCode `2/2` vs baseline `0/2`

![Headline A/B outcomes](docs/evidence/codex-v7/figures/01-headline-outcomes.svg)

These numbers come from the current neutral Codex v7 benchmark: same prompt, same task schema, same repo, same timeout, only SuitCode availability differs.

## Install

Primary install path:

```bash
pipx install git+https://github.com/GreenFuze/suit-code.git
```

Secondary install path:

```bash
uv tool install git+https://github.com/GreenFuze/suit-code.git
```

Then connect SuitCode to your agent with the installer:

```bash
suitcode-install --agent codex
```

Replace `codex` with `claude`, `cursor`, or `all` as needed.

## Connect To Your Agent

### Codex

Install:

```bash
suitcode-install --agent codex
```

Verify:

```bash
codex mcp list
```

Manual fallback:

Windows `~/.codex/config.toml`

```toml
[mcp_servers.suitcode]
transport = "stdio"
command = "cmd"
args = ["/c", "suitcode-mcp"]
enabled = true
```

macOS/Linux `~/.codex/config.toml`

```toml
[mcp_servers.suitcode]
transport = "stdio"
command = "suitcode-mcp"
args = []
enabled = true
```

### Claude Code

Install:

```bash
suitcode-install --agent claude
```

Verify:

```bash
claude mcp list
```

Then open Claude Code and run `/mcp`.

Manual fallback:

Windows

```bash
claude mcp add --transport stdio --scope user suitcode -- cmd /c suitcode-mcp
```

macOS/Linux

```bash
claude mcp add --transport stdio --scope user suitcode -- suitcode-mcp
```

### Cursor

Install:

```bash
suitcode-install --agent cursor
```

Verify:
- restart Cursor
- confirm `suitcode` appears in MCP tools

Manual fallback:

Windows `%USERPROFILE%\\.cursor\\mcp.json`

```json
{
  "mcpServers": {
    "suitcode": {
      "command": "cmd",
      "args": ["/c", "suitcode-mcp"]
    }
  }
}
```

macOS/Linux `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "suitcode": {
      "command": "suitcode-mcp",
      "args": []
    }
  }
}
```

## One End-To-End Example

Prompt:

> A bug report points at `src/suitcode/mcp/service.py`. What owns it, what should I inspect first, and what exact validation set should run before I trust a fix?

SuitCode gives the agent deterministic surfaces for:
- the owning component
- the dependency frontier that defines the debugging surface
- related tests and quality gates
- the minimum verified change set

That lets the agent move from a vague bug report to a bounded validation plan instead of broad file exploration.

Full example:
- [bug-report-to-validation.md](docs/examples/bug-report-to-validation.md)

## Supported Today

Current repository/provider support:
- Python
- npm

Current agent setup paths:
- Codex
- Claude Code
- Cursor

Current analytics/evaluation support:
- Codex: live today
- Claude Code: planned next
- Cursor: planned next

## Evidence

- [Codex v7 evidence summary](docs/evidence/codex-v7/README.md)

The benchmark is neutral A/B on bounded downstream tasks. Tokens are reported as transcript-estimated visible content, not billing totals.

## More Details

- [FEATURES.md](FEATURES.md) for the full feature and MCP tool reference
- [LICENSE.md](LICENSE.md)
