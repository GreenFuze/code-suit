from __future__ import annotations

import shutil

import pytest

from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver


def test_typescript_language_server_resolver_prefers_repository_local_files(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    language_server = repo_root / "node_modules" / ".bin" / "typescript-language-server"
    tsserver = repo_root / "node_modules" / "typescript" / "lib" / "tsserver.js"
    language_server.parent.mkdir(parents=True)
    tsserver.parent.mkdir(parents=True)
    language_server.write_text("", encoding="utf-8")
    tsserver.write_text("", encoding="utf-8")

    resolver = TypeScriptLanguageServerResolver()

    assert resolver.resolve(repo_root) == (
        str(language_server.resolve()),
        "--stdio",
        "--tsserver-path",
        str(tsserver.resolve()),
    )


def test_typescript_language_server_resolver_raises_when_tools_are_missing(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(shutil, "which", lambda command: None)
    resolver = TypeScriptLanguageServerResolver()

    with pytest.raises(ValueError, match="typescript-language-server was not found"):
        resolver.resolve(repo_root)
