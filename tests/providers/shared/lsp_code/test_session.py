from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.providers.shared.lsp_code.session import CoordinatorBackedLspSessionManager, PerCallLspSessionManager
from suitcode.runtime.errors import CoordinatorRuntimeNotReadyError
from suitcode.runtime.models import EnsureServerReadyPayload, ManagedServerState, ManagedServerStatus, ServerFamily


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

    with manager.open_client(tmp_path, tmp_path, _ResolverWithInitOptions(), _factory) as client:
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

    with manager.open_client(tmp_path, tmp_path, _ResolverWithoutInitOptions(), _factory) as client:
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
        with manager.open_client(tmp_path, tmp_path, _FailingResolver(), _factory):
            raise AssertionError("expected resolver failure")
    except ValueError as exc:
        assert "missing language server" in str(exc)


def test_coordinator_backed_session_manager_uses_fallback_for_unknown_resolver(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    manager = CoordinatorBackedLspSessionManager()

    def _factory(command, cwd):
        captured["command"] = command
        captured["cwd"] = cwd
        return _FakeClient()

    with manager.open_client(tmp_path, tmp_path, _ResolverWithoutInitOptions(), _factory) as client:
        assert isinstance(client, _FakeClient)

    assert captured["command"] == ("fake-lsp", "--stdio")
    assert captured["cwd"] == tmp_path.resolve()
    assert client.shutdown_calls == 1


def test_coordinator_backed_session_manager_proxies_supported_resolvers(monkeypatch, tmp_path: Path) -> None:
    class _FakeConnection:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def request(self, request):
            payload = request.model_dump(mode="json")
            self.requests.append(payload)
            kind = payload["kind"]
            if kind == "workspace_symbol":
                return {
                    "items": (
                        {
                            "name": "Core",
                            "kind": 5,
                            "container_name": None,
                            "location": {
                                "uri": (tmp_path / "main.go").resolve().as_uri(),
                                "range": {
                                    "start": {"line": 0, "character": 0},
                                    "end": {"line": 1, "character": 0},
                                },
                            },
                        },
                    )
                }
            return {"items": tuple()}

        def close(self) -> None:
            return None

    class _FakeCoordinatorClient:
        def __init__(self, project_root: Path) -> None:
            self.project_root = project_root
            self.connection = _FakeConnection()

        def ensure_server_ready(self, family: ServerFamily, attachment_root: Path) -> EnsureServerReadyPayload:
            return EnsureServerReadyPayload(
                ready=True,
                status=ManagedServerStatus(
                    family=family,
                    attachment_root=str(attachment_root),
                    state=ManagedServerState.READY,
                ),
                server_family=family,
                attachment_root=str(attachment_root),
            )

        def open_connection(self):
            class _Scope:
                def __enter__(scope_self):
                    return self.connection

                def __exit__(scope_self, exc_type, exc, tb):
                    return False

            return _Scope()

    monkeypatch.setattr(
        "suitcode.providers.shared.lsp_code.session.ProjectCoordinatorClient",
        _FakeCoordinatorClient,
    )

    from suitcode.providers.go.lsp_resolution import GoplsResolver

    manager = CoordinatorBackedLspSessionManager()
    with manager.open_client(tmp_path, tmp_path, GoplsResolver(), lambda command, cwd: _FakeClient()) as client:
        symbols = client.workspace_symbol("Core")

    assert [item.name for item in symbols] == ["Core"]
    assert client._connection.requests[0]["kind"] == "workspace_symbol"
    assert client._connection.requests[0]["family"] == ServerFamily.GOPLS.value


def test_coordinator_backed_session_manager_fails_fast_when_runtime_is_warming(monkeypatch, tmp_path: Path) -> None:
    class _FakeCoordinatorClient:
        def __init__(self, project_root: Path) -> None:
            self.project_root = project_root

        def ensure_server_ready(self, family: ServerFamily, attachment_root: Path) -> EnsureServerReadyPayload:
            return EnsureServerReadyPayload(
                ready=False,
                status=ManagedServerStatus(
                    family=family,
                    attachment_root=str(attachment_root),
                    state=ManagedServerState.WARMING,
                ),
                retry_after_seconds=15,
                server_family=family,
                attachment_root=str(attachment_root),
            )

        def open_connection(self):
            raise AssertionError("open_connection should not run while the runtime is still warming")

    monkeypatch.setattr(
        "suitcode.providers.shared.lsp_code.session.ProjectCoordinatorClient",
        _FakeCoordinatorClient,
    )

    from suitcode.providers.go.lsp_resolution import GoplsResolver

    manager = CoordinatorBackedLspSessionManager()
    with pytest.raises(CoordinatorRuntimeNotReadyError, match="retry after 15s"):
        with manager.open_client(tmp_path, tmp_path, GoplsResolver(), lambda command, cwd: _FakeClient()):
            raise AssertionError("expected readiness preflight failure")
