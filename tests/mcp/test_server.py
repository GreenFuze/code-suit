from __future__ import annotations
import sys
from pathlib import Path

import pytest

from suitcode.mcp.server import build_arg_parser, main, managed_pid_file


class _FakeApp:
    def __init__(self) -> None:
        self.settings = type("Settings", (), {"host": "127.0.0.1", "port": 8000, "stateless_http": False})()
        self.calls: list[str] = []

    def run(self, transport: str) -> None:
        self.calls.append(transport)


def test_build_arg_parser_defaults() -> None:
    args = build_arg_parser().parse_args([])

    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.pid_file is None
    assert args.replace_existing is False


def test_main_runs_stdio(monkeypatch) -> None:
    fake_app = _FakeApp()
    monkeypatch.setattr("suitcode.mcp.server.create_mcp_app", lambda: fake_app)
    entered: list[tuple[str | None, bool]] = []

    class _ManagedPidFile:
        def __init__(self, pid_file: str | None, replace_existing: bool) -> None:
            self._pid_file = pid_file
            self._replace_existing = replace_existing

        def __enter__(self):
            entered.append((self._pid_file, self._replace_existing))
            return None

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("suitcode.mcp.server.managed_pid_file", _ManagedPidFile)
    monkeypatch.setattr(sys, "argv", ["suitcode-mcp"])

    main()

    assert entered == [(None, False)]
    assert fake_app.calls == ["stdio"]


def test_main_runs_http(monkeypatch) -> None:
    fake_app = _FakeApp()
    monkeypatch.setattr("suitcode.mcp.server.create_mcp_app", lambda: fake_app)
    entered: list[tuple[str | None, bool]] = []

    class _ManagedPidFile:
        def __init__(self, pid_file: str | None, replace_existing: bool) -> None:
            self._pid_file = pid_file
            self._replace_existing = replace_existing

        def __enter__(self):
            entered.append((self._pid_file, self._replace_existing))
            return None

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("suitcode.mcp.server.managed_pid_file", _ManagedPidFile)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "suitcode-mcp",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--pid-file",
            "server.pid",
            "--replace-existing",
        ],
    )

    main()

    assert entered == [("server.pid", True)]
    assert fake_app.settings.host == "0.0.0.0"
    assert fake_app.settings.port == 9000
    assert fake_app.settings.stateless_http is True
    assert fake_app.calls == ["streamable-http"]


def test_managed_pid_file_writes_and_removes_current_pid(tmp_path: Path) -> None:
    pid_file = tmp_path / "mcp.pid"

    with managed_pid_file(str(pid_file), replace_existing=False):
        assert pid_file.exists()

    assert not pid_file.exists()


def test_managed_pid_file_raises_for_running_existing_process(tmp_path: Path, monkeypatch) -> None:
    pid_file = tmp_path / "mcp.pid"
    pid_file.write_text("99999", encoding="utf-8")
    monkeypatch.setattr("suitcode.mcp.server._is_process_running", lambda pid: True)

    with pytest.raises(RuntimeError, match="already appears to be running"):
        with managed_pid_file(str(pid_file), replace_existing=False):
            pass
