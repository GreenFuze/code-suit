from __future__ import annotations

import shutil
import subprocess

import pytest

from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver


def test_typescript_language_server_resolver_prefers_repository_local_files(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    language_server = repo_root / "node_modules" / ".bin" / "typescript-language-server"
    cli_module = repo_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
    tsserver = repo_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
    language_server.parent.mkdir(parents=True)
    cli_module.parent.mkdir(parents=True, exist_ok=True)
    tsserver.parent.mkdir(parents=True)
    language_server.write_text("", encoding="utf-8")
    cli_module.write_text("", encoding="utf-8")
    tsserver.write_text("", encoding="utf-8")

    resolver = TypeScriptLanguageServerResolver()

    assert resolver.resolve(repo_root) == (
        shutil.which("node"),
        str(cli_module.resolve()),
        "--stdio",
    )


def test_typescript_language_server_resolver_raises_when_tools_are_missing(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("SUITCODE_TOOL_CACHE_DIR", str(tmp_path / "empty-cache"))
    monkeypatch.setattr(shutil, "which", lambda command: None)
    resolver = TypeScriptLanguageServerResolver()

    with pytest.raises(ValueError, match="typescript-language-server was not found|npm was not found for managed TypeScript language-server provisioning"):
        resolver.resolve(repo_root)


def test_typescript_language_server_resolver_falls_back_to_windows_node_locations(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    cli_module = repo_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
    tsserver = repo_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
    cli_module.parent.mkdir(parents=True)
    tsserver.parent.mkdir(parents=True)
    cli_module.write_text("", encoding="utf-8")
    tsserver.write_text("", encoding="utf-8")

    node_root = tmp_path / "ProgramFiles" / "nodejs"
    node_root.mkdir(parents=True)
    node_executable = node_root / "node.exe"
    node_executable.write_text("", encoding="utf-8")

    monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "ProgramFiles"))

    resolver = TypeScriptLanguageServerResolver()

    assert resolver.resolve(repo_root) == (
        str(node_executable.resolve()),
        str(cli_module.resolve()),
        "--stdio",
    )


def test_typescript_language_server_resolver_provisions_managed_toolchain(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tsserver = repo_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
    tsserver.parent.mkdir(parents=True)
    tsserver.write_text("", encoding="utf-8")

    cache_root = tmp_path / "tool-cache"
    node_executable = tmp_path / "node.exe"
    npm_executable = tmp_path / "npm.cmd"
    node_executable.write_text("", encoding="utf-8")
    npm_executable.write_text("", encoding="utf-8")

    def _which(command: str) -> str | None:
        mapping = {
            "node": str(node_executable.resolve()),
            "npm.cmd": str(npm_executable.resolve()),
            "npm": str(npm_executable.resolve()),
        }
        return mapping.get(command)

    def _run(command, cwd=None, check=None, stdout=None, stderr=None, text=None):
        managed_root = cwd
        cli_module = managed_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
        managed_tsserver = managed_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
        cli_module.parent.mkdir(parents=True, exist_ok=True)
        managed_tsserver.parent.mkdir(parents=True, exist_ok=True)
        cli_module.write_text("", encoding="utf-8")
        managed_tsserver.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("SUITCODE_TOOL_CACHE_DIR", str(cache_root))
    monkeypatch.setattr(shutil, "which", _which)
    monkeypatch.setattr(subprocess, "run", _run)

    resolver = TypeScriptLanguageServerResolver()

    command = resolver.resolve(repo_root)
    init_options = resolver.resolve_initialization_options(repo_root)

    assert command[0] == str(node_executable.resolve())
    assert command[2] == "--stdio"
    assert "typescript-language-server" in command[1]
    assert init_options["tsserver"]["path"] == str(tsserver.resolve())


def test_typescript_language_server_resolver_uses_managed_tsserver_when_local_is_missing(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_root = tmp_path / "tool-cache"
    node_executable = tmp_path / "node.exe"
    npm_executable = tmp_path / "npm.cmd"
    node_executable.write_text("", encoding="utf-8")
    npm_executable.write_text("", encoding="utf-8")

    def _which(command: str) -> str | None:
        mapping = {
            "node": str(node_executable.resolve()),
            "npm.cmd": str(npm_executable.resolve()),
            "npm": str(npm_executable.resolve()),
        }
        return mapping.get(command)

    def _run(command, cwd=None, check=None, stdout=None, stderr=None, text=None):
        managed_root = cwd
        cli_module = managed_root / "node_modules" / "typescript-language-server" / "lib" / "cli.mjs"
        managed_tsserver = managed_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
        cli_module.parent.mkdir(parents=True, exist_ok=True)
        managed_tsserver.parent.mkdir(parents=True, exist_ok=True)
        cli_module.write_text("", encoding="utf-8")
        managed_tsserver.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("SUITCODE_TOOL_CACHE_DIR", str(cache_root))
    monkeypatch.setattr(shutil, "which", _which)
    monkeypatch.setattr(subprocess, "run", _run)

    resolver = TypeScriptLanguageServerResolver()
    init_options = resolver.resolve_initialization_options(repo_root)

    assert "tool-cache" in init_options["tsserver"]["path"]
