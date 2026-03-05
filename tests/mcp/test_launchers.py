from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_run_mcp_bat_contains_expected_defaults() -> None:
    content = Path("run_mcp.bat").read_text(encoding="utf-8")

    assert "suitcode.mcp.server" in content
    assert "--transport http" in content
    assert "--host 127.0.0.1" in content
    assert "--port 8000" not in content
    assert "%*" in content
    assert ".venv\\Scripts\\python.exe" in content


def test_run_mcp_sh_contains_expected_defaults() -> None:
    content = Path("run_mcp.sh").read_text(encoding="utf-8")

    assert "suitcode.mcp.server" in content
    assert "--transport http" in content
    assert "--host 127.0.0.1" in content
    assert "--port 8000" not in content
    assert '"$@"' in content
    assert ".venv/bin/python" in content


def test_run_mcp_bat_help_on_windows() -> None:
    if os.name != "nt":
        return

    completed = subprocess.run(
        ["cmd", "/c", "run_mcp.bat", "--help"],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0


def test_run_mcp_sh_help_on_non_windows() -> None:
    if os.name == "nt":
        return

    completed = subprocess.run(
        ["bash", "run_mcp.sh", "--help"],
        cwd=str(Path.cwd()),
        env={**os.environ, "PYTHONPATH": f"{Path.cwd() / 'src'}{os.pathsep}{os.environ.get('PYTHONPATH', '')}".strip(os.pathsep)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    output = completed.stdout + completed.stderr
    assert "suitcode-mcp" in output
