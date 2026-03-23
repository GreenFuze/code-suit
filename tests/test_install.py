from __future__ import annotations

import json
from pathlib import Path

import pytest

from suitcode import install


def test_codex_install_creates_config_and_preserves_other_servers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[mcp_servers.other]\ncommand = \"python\"\nargs = [\"-m\", \"other\"]\nenabled = true\n",
        encoding="utf-8",
    )
    context = install.InstallContext(home=home, os_name="nt", server_name="suitcode")

    result = install._apply_codex(context=context, dry_run=False, uninstall=False)

    content = config_path.read_text(encoding="utf-8")
    assert result.changed is True
    assert "[mcp_servers.other]" in content
    assert "[mcp_servers.suitcode]" in content
    assert 'command = "cmd"' in content
    assert 'args = ["/c", "suitcode-mcp"]' in content
    assert any(path.name.startswith("config.toml.bak.") for path in config_path.parent.iterdir())


def test_codex_uninstall_removes_only_suitcode(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "[mcp_servers.suitcode]",
                'command = "cmd"',
                'args = ["/c", "suitcode-mcp"]',
                "enabled = true",
                "",
                "[mcp_servers.other]",
                'command = "python"',
                'args = ["-m", "other"]',
                "enabled = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    context = install.InstallContext(home=home, os_name="nt", server_name="suitcode")

    install._apply_codex(context=context, dry_run=False, uninstall=True)

    content = config_path.read_text(encoding="utf-8")
    assert "[mcp_servers.suitcode]" not in content
    assert "[mcp_servers.other]" in content


def test_cursor_install_creates_config_and_preserves_other_servers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".cursor" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"mcpServers": {"other": {"command": "python", "args": ["-m", "other"]}}}), encoding="utf-8")
    context = install.InstallContext(home=home, os_name="posix", server_name="suitcode")

    result = install._apply_cursor(context=context, dry_run=False, uninstall=False)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert result.changed is True
    assert payload["mcpServers"]["other"]["command"] == "python"
    assert payload["mcpServers"]["suitcode"] == {"command": "suitcode-mcp", "args": []}
    assert any(path.name.startswith("mcp.json.bak.") for path in config_path.parent.iterdir())


def test_dry_run_does_not_mutate_codex_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_path = home / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("[mcp_servers.other]\ncommand = \"python\"\n", encoding="utf-8")
    original = config_path.read_text(encoding="utf-8")
    context = install.InstallContext(home=home, os_name="posix", server_name="suitcode")

    result = install._apply_codex(context=context, dry_run=True, uninstall=False)

    assert result.message.startswith("dry-run:")
    assert config_path.read_text(encoding="utf-8") == original


def test_server_command_shapes() -> None:
    assert install._server_command("nt") == "cmd"
    assert install._server_args("nt") == ["/c", "suitcode-mcp"]
    assert install._server_command("posix") == "suitcode-mcp"
    assert install._server_args("posix") == []


def test_claude_install_invokes_expected_cli(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    context = install.InstallContext(home=tmp_path, os_name="posix", server_name="suitcode")

    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool):
        calls.append(command)
        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""
        return _Completed()

    monkeypatch.setattr(install.subprocess, "run", fake_run)

    result = install._apply_claude(context=context, dry_run=False, uninstall=False, force=False)

    assert result.changed is True
    assert calls == [[
        "/usr/bin/claude", "mcp", "add", "--transport", "stdio", "--scope", "user",
        "suitcode", "--", "suitcode-mcp",
    ]]


def test_claude_install_handles_missing_cli(tmp_path: Path, monkeypatch) -> None:
    context = install.InstallContext(home=tmp_path, os_name="posix", server_name="suitcode")
    monkeypatch.setattr(install.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="`claude` CLI not found"):
        install._apply_claude(context=context, dry_run=False, uninstall=False, force=False)


def test_agent_all_returns_nonzero_if_any_agent_fails(monkeypatch, capsys) -> None:
    def fake_apply_for_agent(*, agent: str, context, dry_run: bool, uninstall: bool, force: bool):
        if agent == "claude":
            raise RuntimeError("broken")
        return install.InstallResult(agent=agent, changed=True, message="ok")

    monkeypatch.setattr(install, "_apply_for_agent", fake_apply_for_agent)

    exit_code = install.main(["--agent", "all", "--dry-run"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "[codex] ok" in captured.out
    assert "[cursor] ok" in captured.out
    assert "[claude] broken" in captured.err


def test_pyproject_exposes_install_script() -> None:
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'suitcode-install = "suitcode.install:main"' in content
    assert 'suitcode-mcp = "suitcode.mcp.server:main"' in content
