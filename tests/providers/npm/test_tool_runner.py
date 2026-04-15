from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from suitcode.providers.npm.tool_runner import TypeScriptProbeRunner, TypeScriptToolTimeoutError


def test_typescript_probe_runner_times_out(monkeypatch, tmp_path: Path) -> None:
    runner = TypeScriptProbeRunner(
        repository_root=tmp_path,
        attachment_root=tmp_path,
        timeout_seconds=0.01,
    )
    monkeypatch.setattr(runner, "resolve_node_path", lambda: "node")
    monkeypatch.setattr(runner, "resolve_typescript_library_path", lambda: "typescript.js")

    def _run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="node probe", timeout=0.01)

    monkeypatch.setattr("suitcode.providers.npm.tool_runner.subprocess.run", _run)

    with pytest.raises(TypeScriptToolTimeoutError, match="timed out"):
        runner.run_json_probe(
            script_name="ts_symbols.cjs",
            command_args=("repo", "file", "typescript.js"),
            error_label="TypeScript symbols",
        )
