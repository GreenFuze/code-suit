from __future__ import annotations

import shutil

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
    monkeypatch.setattr(shutil, "which", lambda command: None)
    resolver = TypeScriptLanguageServerResolver()

    with pytest.raises(ValueError, match="typescript-language-server was not found"):
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
