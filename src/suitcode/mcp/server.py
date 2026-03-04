from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path

from suitcode.mcp.app import create_mcp_app


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suitcode-mcp")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--pid-file")
    parser.add_argument("--replace-existing", action="store_true")
    return parser


@contextlib.contextmanager
def managed_pid_file(pid_file: str | None, replace_existing: bool):
    if pid_file is None:
        yield
        return

    pid_path = Path(pid_file).expanduser().resolve()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()
    existing_pid = _read_pid(pid_path)
    if existing_pid is not None and existing_pid != current_pid and _is_process_running(existing_pid):
        if not replace_existing:
            raise RuntimeError(
                f"MCP server already appears to be running with pid {existing_pid}. "
                "Use --replace-existing or remove the stale pid file."
            )
        _terminate_process(existing_pid)

    pid_path.write_text(str(current_pid), encoding="utf-8")
    try:
        yield
    finally:
        if _read_pid(pid_path) == current_pid:
            pid_path.unlink(missing_ok=True)


def _read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    content = pid_path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    try:
        return int(content)
    except ValueError as exc:
        raise RuntimeError(f"Invalid pid file contents in `{pid_path}`") from exc


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process(pid: int) -> None:
    if pid <= 0:
        raise RuntimeError(f"Invalid pid `{pid}`")
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode not in (0, 128):
            raise RuntimeError(f"Failed to terminate existing MCP server pid {pid}: {completed.stderr.strip()}")
        return

    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _is_process_running(pid):
            return
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    with managed_pid_file(args.pid_file, args.replace_existing):
        app = create_mcp_app()
        if args.transport == "http":
            app.settings.host = args.host
            app.settings.port = args.port
            app.settings.stateless_http = True
            app.run(transport="streamable-http")
            return

        app.run(transport="stdio")


if __name__ == "__main__":
    main()
