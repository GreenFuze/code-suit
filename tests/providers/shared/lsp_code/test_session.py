from __future__ import annotations

from pathlib import Path

from suitcode.providers.shared.lsp_code.session import PerCallLspSessionManager


class _FakeClient:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class _ResolverWithInitOptions:
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        return ("fake-lsp", "--stdio")

    def resolve_initialization_options(self, repository_root: Path) -> dict[str, object]:
        return {"x": 1}


class _ResolverWithoutInitOptions:
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        return ("fake-lsp", "--stdio")


def test_per_call_session_manager_passes_initialization_options_when_supported(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    manager = PerCallLspSessionManager()

    def _factory(command, cwd, initialization_options):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["initialization_options"] = initialization_options
        return _FakeClient()

    with manager.open_client(tmp_path, _ResolverWithInitOptions(), _factory) as client:
        assert isinstance(client, _FakeClient)

    assert captured["command"] == ("fake-lsp", "--stdio")
    assert captured["cwd"] == tmp_path.resolve()
    assert captured["initialization_options"] == {"x": 1}
    assert client.shutdown_calls == 1


def test_per_call_session_manager_falls_back_to_two_argument_factory(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    manager = PerCallLspSessionManager()

    def _factory(command, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        return _FakeClient()

    with manager.open_client(tmp_path, _ResolverWithoutInitOptions(), _factory) as client:
        assert isinstance(client, _FakeClient)

    assert captured["command"] == ("fake-lsp", "--stdio")
    assert captured["cwd"] == tmp_path.resolve()
    assert client.shutdown_calls == 1


def test_per_call_session_manager_propagates_resolver_fail_fast(tmp_path: Path) -> None:
    class _FailingResolver:
        def resolve(self, repository_root: Path) -> tuple[str, ...]:
            raise ValueError("missing language server")

    manager = PerCallLspSessionManager()

    def _factory(command, cwd):
        raise AssertionError("factory should not be called when resolver fails")

    try:
        with manager.open_client(tmp_path, _FailingResolver(), _factory):
            raise AssertionError("expected resolver failure")
    except ValueError as exc:
        assert "missing language server" in str(exc)
