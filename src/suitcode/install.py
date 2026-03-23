from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstallContext:
    home: Path
    os_name: str
    server_name: str


@dataclass(frozen=True)
class InstallResult:
    agent: str
    changed: bool
    message: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="suitcode-install")
    parser.add_argument("--agent", choices=("codex", "claude", "cursor", "all"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--server-name", default="suitcode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    context = InstallContext(
        home=Path.home(),
        os_name=os.name,
        server_name=args.server_name,
    )
    agents = ("codex", "claude", "cursor") if args.agent == "all" else (args.agent,)
    failures: list[str] = []
    for agent in agents:
        try:
            result = _apply_for_agent(
                agent=agent,
                context=context,
                dry_run=args.dry_run,
                uninstall=args.uninstall,
                force=args.force,
            )
            print(f"[{result.agent}] {result.message}")
            print(_verification_hint(agent))
        except Exception as exc:  # pragma: no cover - exercised through targeted tests
            failures.append(agent)
            print(f"[{agent}] {exc}", file=sys.stderr)
    return 1 if failures else 0


def _apply_for_agent(
    *,
    agent: str,
    context: InstallContext,
    dry_run: bool,
    uninstall: bool,
    force: bool,
) -> InstallResult:
    if agent == "codex":
        return _apply_codex(context=context, dry_run=dry_run, uninstall=uninstall)
    if agent == "claude":
        return _apply_claude(context=context, dry_run=dry_run, uninstall=uninstall, force=force)
    if agent == "cursor":
        return _apply_cursor(context=context, dry_run=dry_run, uninstall=uninstall)
    raise ValueError(f"unsupported agent: {agent}")


def _apply_codex(*, context: InstallContext, dry_run: bool, uninstall: bool) -> InstallResult:
    config_path = context.home / ".codex" / "config.toml"
    payload = _read_toml_file(config_path)
    mcp_servers = payload.setdefault("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        raise RuntimeError(f"invalid Codex config: `mcp_servers` is not a table in `{config_path}`")
    changed = False
    if uninstall:
        if context.server_name in mcp_servers:
            del mcp_servers[context.server_name]
            changed = True
        action = "remove"
    else:
        server_payload = {
            "transport": "stdio",
            "command": _server_command(context.os_name),
            "args": _server_args(context.os_name),
            "enabled": True,
        }
        if mcp_servers.get(context.server_name) != server_payload:
            mcp_servers[context.server_name] = server_payload
            changed = True
        action = "install"
    if dry_run:
        return InstallResult("codex", changed, f"dry-run: would {action} `{context.server_name}` in `{config_path}`")
    if changed:
        _backup_if_exists(config_path)
        _write_text(config_path, _dump_toml(payload))
    return InstallResult("codex", changed, f"{action}ed `{context.server_name}` in `{config_path}`")


def _apply_cursor(*, context: InstallContext, dry_run: bool, uninstall: bool) -> InstallResult:
    config_path = context.home / ".cursor" / "mcp.json"
    payload = _read_json_file(config_path)
    servers = payload.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"invalid Cursor config: `mcpServers` is not an object in `{config_path}`")
    changed = False
    if uninstall:
        if context.server_name in servers:
            del servers[context.server_name]
            changed = True
        action = "remove"
    else:
        server_payload = {
            "command": _server_command(context.os_name),
            "args": _server_args(context.os_name),
        }
        if servers.get(context.server_name) != server_payload:
            servers[context.server_name] = server_payload
            changed = True
        action = "install"
    if dry_run:
        return InstallResult("cursor", changed, f"dry-run: would {action} `{context.server_name}` in `{config_path}`")
    if changed:
        _backup_if_exists(config_path)
        _write_text(config_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return InstallResult("cursor", changed, f"{action}ed `{context.server_name}` in `{config_path}`")


def _apply_claude(*, context: InstallContext, dry_run: bool, uninstall: bool, force: bool) -> InstallResult:
    claude_binary = shutil.which("claude")
    if not claude_binary and not dry_run:
        raise RuntimeError("`claude` CLI not found on PATH")
    command = [claude_binary or "claude", "mcp"]
    if uninstall:
        full_command = [*command, "remove", context.server_name]
        if dry_run:
            return InstallResult("claude", True, f"dry-run: would run `{_format_command(full_command)}`")
        _run_subprocess(full_command)
        return InstallResult("claude", True, f"removed `{context.server_name}` via Claude Code CLI")
    base_add = [
        *command,
        "add",
        "--transport",
        "stdio",
        "--scope",
        "user",
        context.server_name,
        "--",
        _server_command(context.os_name),
        *_server_args(context.os_name),
    ]
    if dry_run:
        return InstallResult("claude", True, f"dry-run: would run `{_format_command(base_add)}`")
    if force:
        _run_subprocess([*command, "remove", context.server_name], allow_failure=True)
    completed = _run_subprocess(base_add, allow_failure=not force)
    if completed.returncode != 0:
        raise RuntimeError("Claude Code MCP add failed; rerun with `--force` if an existing entry must be replaced")
    return InstallResult("claude", True, f"installed `{context.server_name}` via Claude Code CLI")


def _verification_hint(agent: str) -> str:
    if agent == "codex":
        return "  verify: `codex mcp list`"
    if agent == "claude":
        return "  verify: `claude mcp list` and then `/mcp` inside Claude Code"
    if agent == "cursor":
        return "  verify: restart Cursor and confirm SuitCode appears in MCP tools"
    return ""


def _server_command(os_name: str) -> str:
    return "cmd" if os_name == "nt" else "suitcode-mcp"


def _server_args(os_name: str) -> list[str]:
    return ["/c", "suitcode-mcp"] if os_name == "nt" else []


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid JSON config root in `{path}`")
    return payload


def _read_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid TOML config root in `{path}`")
    return payload


def _backup_if_exists(path: Path) -> None:
    if not path.exists():
        return
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dump_toml(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    _emit_toml_table(lines, (), payload)
    return "\n".join(lines).rstrip() + "\n"


def _emit_toml_table(lines: list[str], path: tuple[str, ...], table: dict[str, Any]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    child_items: list[tuple[str, dict[str, Any]]] = []
    for key, value in table.items():
        if isinstance(value, dict):
            child_items.append((key, value))
        else:
            scalar_items.append((key, value))
    if path:
        if lines:
            lines.append("")
        lines.append(f"[{'.'.join(path)}]")
    for key, value in scalar_items:
        lines.append(f"{key} = {_format_toml_value(value)}")
    for key, child in child_items:
        _emit_toml_table(lines, (*path, key), child)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value)!r}")


def _run_subprocess(command: list[str], allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 and not allow_failure:
        stderr = completed.stderr.strip() or completed.stdout.strip() or f"command failed: {_format_command(command)}"
        raise RuntimeError(stderr)
    return completed


def _format_command(command: list[str]) -> str:
    return " ".join(command)


if __name__ == "__main__":
    raise SystemExit(main())
