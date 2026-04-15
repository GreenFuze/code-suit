from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from suitcode.providers.shared.lsp import (
    LspDocumentSymbol,
    LspLocation,
    LspPosition,
    LspRange,
    LspWorkspaceSymbol,
)
from suitcode.runtime.client import ProjectCoordinatorClient
from suitcode.runtime.coordinator import CoordinatorServer, _ManagedLspSession
from suitcode.runtime.discovery import CoordinatorDiscoveryStore
from suitcode.runtime.errors import CoordinatorUnavailableError
from suitcode.runtime.errors import CoordinatorRuntimeNotReadyError
from suitcode.runtime.models import CoordinatorState, ManagedServerState, ServerFamily
from suitcode.runtime.versioning import PROTOCOL_VERSION, build_version


class _FakeRuntimeLspClient:
    def __init__(self, command, cwd, initialization_options=None) -> None:
        self.command = command
        self.cwd = cwd
        self.initialization_options = initialization_options
        self.initialized_with: Path | None = None
        self.shutdown_calls = 0

    def initialize(self, root_path: Path) -> None:
        self.initialized_with = root_path

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        return (
            LspWorkspaceSymbol(
                name=query,
                kind=5,
                container_name=None,
                location=LspLocation(
                    uri=(self.cwd / "main.go").resolve().as_uri(),
                    range=LspRange(
                        start=LspPosition(line=0, character=0),
                        end=LspPosition(line=1, character=0),
                    ),
                ),
            ),
        )

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        return (
            LspDocumentSymbol(
                name=file_path.stem,
                kind=12,
                detail=None,
                range=LspRange(
                    start=LspPosition(line=0, character=0),
                    end=LspPosition(line=0, character=4),
                ),
                selection_range=LspRange(
                    start=LspPosition(line=0, character=0),
                    end=LspPosition(line=0, character=4),
                ),
            ),
        )

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return (
            LspLocation(
                uri=file_path.resolve().as_uri(),
                range=LspRange(
                    start=LspPosition(line=line - 1, character=column - 1),
                    end=LspPosition(line=line, character=column),
                ),
            ),
        )

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False) -> tuple[LspLocation, ...]:
        return self.definition(file_path, line, column)

    def implementation(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return self.definition(file_path, line, column)

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class _TimeoutRuntimeLspClient(_FakeRuntimeLspClient):
    def document_symbol(self, file_path: Path):  # noqa: ARG002
        from suitcode.providers.shared.lsp.errors import LspTimeoutError

        raise LspTimeoutError("language server timed out waiting for `textDocument/documentSymbol` after 20s")


def test_project_coordinator_client_bootstraps_and_returns_status(monkeypatch, tmp_path: Path) -> None:
    _patch_runtime(monkeypatch, tmp_path)
    threads: list[threading.Thread] = []
    servers: list[CoordinatorServer] = []

    def _spawn_candidate(self, instance_id: str) -> None:
        server = CoordinatorServer(project_root=tmp_path, instance_id=instance_id, idle_ttl_seconds=30.0)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)

    monkeypatch.setattr(ProjectCoordinatorClient, "_spawn_candidate", _spawn_candidate)

    client = ProjectCoordinatorClient(tmp_path)
    status = client.get_runtime_status()

    assert status.canonical_project_root == str(tmp_path.resolve())
    assert status.protocol_version == PROTOCOL_VERSION
    assert status.build_version == build_version()
    assert status.state in {CoordinatorState.STARTING, CoordinatorState.READY, CoordinatorState.WARMING}

    for server in servers:
        server.shutdown()
    for thread in threads:
        thread.join(timeout=5.0)


def test_project_coordinator_client_ensure_server_ready_reports_warming_retry_state(monkeypatch, tmp_path: Path) -> None:
    init_started = threading.Event()
    release_initialize = threading.Event()

    class _BlockingRuntimeLspClient(_FakeRuntimeLspClient):
        def initialize(self, root_path: Path) -> None:
            init_started.set()
            release_initialize.wait(timeout=5.0)
            super().initialize(root_path)

    _patch_runtime(monkeypatch, tmp_path, lsp_client_cls=_BlockingRuntimeLspClient)
    servers: list[CoordinatorServer] = []
    threads: list[threading.Thread] = []

    def _spawn_candidate(self, instance_id: str) -> None:
        server = CoordinatorServer(project_root=tmp_path, instance_id=instance_id, idle_ttl_seconds=30.0)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)

    monkeypatch.setattr(ProjectCoordinatorClient, "_spawn_candidate", _spawn_candidate)

    attachment_root = tmp_path / "go-app"
    attachment_root.mkdir(parents=True)
    (attachment_root / "main.go").write_text("package main\n", encoding="utf-8")

    client = ProjectCoordinatorClient(tmp_path)
    payload = client.ensure_server_ready(ServerFamily.GOPLS, attachment_root)

    assert init_started.wait(timeout=5.0) is True
    assert payload.ready is False
    assert payload.status.family == ServerFamily.GOPLS
    assert payload.status.attachment_root == str(attachment_root.resolve())
    assert payload.status.state == ManagedServerState.WARMING
    assert payload.retry_after_seconds == 15
    assert payload.server_family == ServerFamily.GOPLS
    assert payload.attachment_root == str(attachment_root.resolve())

    release_initialize.set()

    for server in servers:
        server.shutdown()
    for thread in threads:
        thread.join(timeout=5.0)


def test_managed_session_readiness_payload_reports_degraded_retry_window(tmp_path: Path) -> None:
    session = _ManagedLspSession(
        family=ServerFamily.GOPLS,
        attachment_root=tmp_path,
        idle_ttl_seconds=60.0,
    )
    session.state = ManagedServerState.DEGRADED
    session.next_retry_at = time.time() + 7.2

    payload = session.readiness_payload()

    assert payload.ready is False
    assert payload.status.state == ManagedServerState.DEGRADED
    assert 1 <= (payload.retry_after_seconds or 0) <= 60


def test_managed_session_readiness_payload_reports_ready_without_retry(tmp_path: Path) -> None:
    session = _ManagedLspSession(
        family=ServerFamily.GOPLS,
        attachment_root=tmp_path,
        idle_ttl_seconds=60.0,
    )
    session.state = ManagedServerState.READY
    session.last_activity_at = time.time()
    session._client = object()  # type: ignore[assignment]

    payload = session.readiness_payload()

    assert payload.ready is True
    assert payload.status.state == ManagedServerState.READY
    assert payload.retry_after_seconds is None


def test_managed_session_request_timeout_marks_session_degraded(tmp_path: Path) -> None:
    session = _ManagedLspSession(
        family=ServerFamily.GOPLS,
        attachment_root=tmp_path,
        idle_ttl_seconds=60.0,
    )
    session.state = ManagedServerState.READY
    session.last_activity_at = time.time()
    session._client = _TimeoutRuntimeLspClient(("fake",), tmp_path)  # type: ignore[assignment]

    with pytest.raises(CoordinatorRuntimeNotReadyError) as exc_info:
        session.document_symbol(tmp_path / "main.go")

    assert exc_info.value.state == ManagedServerState.DEGRADED
    assert exc_info.value.retry_after_seconds >= 1
    assert session.status().state == ManagedServerState.DEGRADED


def test_project_coordinator_client_shutdown_stops_runtime(monkeypatch, tmp_path: Path) -> None:
    _patch_runtime(monkeypatch, tmp_path)
    servers: list[CoordinatorServer] = []
    threads: list[threading.Thread] = []

    def _spawn_candidate(self, instance_id: str) -> None:
        server = CoordinatorServer(project_root=tmp_path, instance_id=instance_id, idle_ttl_seconds=30.0)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)

    monkeypatch.setattr(ProjectCoordinatorClient, "_spawn_candidate", _spawn_candidate)

    client = ProjectCoordinatorClient(tmp_path)
    status = client.get_runtime_status()
    assert status.state in {CoordinatorState.STARTING, CoordinatorState.READY, CoordinatorState.WARMING}

    client.shutdown()

    for thread in threads:
        thread.join(timeout=5.0)

    assert all(not thread.is_alive() for thread in threads)


def test_project_coordinator_client_shutdown_is_idempotent_when_runtime_is_already_gone(monkeypatch, tmp_path: Path) -> None:
    client = ProjectCoordinatorClient(tmp_path)
    monkeypatch.setattr(
        client,
        "_current_status_record",
        lambda: type("Record", (), {"endpoint": client.endpoint_uri, "pid": 424242, "instance_id": "gone"})(),
    )
    monkeypatch.setattr("suitcode.runtime.client.is_process_running", lambda pid: False)
    removed: list[str] = []
    monkeypatch.setattr(CoordinatorDiscoveryStore, "remove_if_owned", lambda self, instance_id: removed.append(instance_id))
    monkeypatch.setattr(
        client,
        "_connect_to_coordinator_with_retries",
        lambda endpoint_uri, attempts=2: (_ for _ in ()).throw(CoordinatorUnavailableError("gone")),
    )

    client.shutdown()

    assert removed == ["gone"]


def test_spawn_candidate_injects_source_root_into_pythonpath(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FakeProcess:
        def poll(self):
            return None

    def _fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr("suitcode.runtime.client.subprocess.Popen", _fake_popen)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(("C:\\existing", "C:\\other")))

    client = ProjectCoordinatorClient(tmp_path)
    process = client._spawn_candidate("abc123")

    assert process is not None
    assert captured["command"][0].endswith("python.exe")
    assert captured["command"][1:4] == ["-m", "suitcode.runtime.main", "--project-root"]
    assert captured["kwargs"]["cwd"] == str(tmp_path.resolve())
    pythonpath = captured["kwargs"]["env"]["PYTHONPATH"]
    assert str(Path(__file__).resolve().parents[2] / "src") == pythonpath.split(os.pathsep)[0]
    assert "C:\\existing" in pythonpath


def test_wait_for_winner_fails_fast_when_candidate_exits_before_discovery(monkeypatch, tmp_path: Path) -> None:
    class _ExitedProcess:
        def poll(self):
            return 7

    client = ProjectCoordinatorClient(tmp_path)
    monkeypatch.setattr(
        client,
        "_connect_to_coordinator",
        lambda endpoint_uri: (_ for _ in ()).throw(CoordinatorUnavailableError("not ready")),
    )
    with pytest.raises(CoordinatorUnavailableError, match="exited before binding the project endpoint"):
        client._wait_for_coordinator(_ExitedProcess())


def test_ensure_coordinator_waits_for_startup_while_holding_project_lock(monkeypatch, tmp_path: Path) -> None:
    lock_state = {"held": False}

    @contextmanager
    def _fake_project_lock(path, instance_id, timeout_seconds=15.0):  # noqa: ANN001, ARG001
        assert lock_state["held"] is False
        lock_state["held"] = True
        try:
            yield
        finally:
            lock_state["held"] = False

    client = ProjectCoordinatorClient(tmp_path)
    monkeypatch.setattr("suitcode.runtime.client.project_lock", _fake_project_lock)
    monkeypatch.setattr(client, "_probe_existing_coordinator", lambda: CoordinatorUnavailableError("missing"))
    monkeypatch.setattr(client, "_replace_or_cleanup_locked", lambda error: None)
    monkeypatch.setattr(client, "_spawn_candidate", lambda instance_id: object())

    called = {"wait": False}

    def _fake_wait(candidate_process):  # noqa: ANN001
        assert lock_state["held"] is True
        assert candidate_process is not None
        called["wait"] = True

    monkeypatch.setattr(client, "_wait_for_coordinator", _fake_wait)

    client._ensure_coordinator()
    assert called["wait"] is True


def test_coordinator_run_shuts_down_immediately_when_publish_loses_election(monkeypatch, tmp_path: Path) -> None:
    class _FakeListener:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    listener = _FakeListener()
    cleanup_calls: list[str] = []

    monkeypatch.setattr("suitcode.runtime.coordinator.listen_on_endpoint", lambda endpoint: listener)
    monkeypatch.setattr("suitcode.runtime.coordinator.cleanup_endpoint", lambda endpoint: cleanup_calls.append(endpoint))

    server = CoordinatorServer(project_root=tmp_path, instance_id="winner-lost")

    def _publish() -> None:
        server._stop_event.set()

    monkeypatch.setattr(server, "_publish_discovery", _publish)
    monkeypatch.setattr(server, "_schedule_warmups", lambda: pytest.fail("warmups should not start for a losing coordinator"))
    monkeypatch.setattr(server, "_serve", lambda: pytest.fail("losing coordinator should not enter serve loop"))

    server.run()

    assert listener.closed is True
    assert len(cleanup_calls) == 1


def test_runtime_main_imports_in_fresh_process(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root / "src")

    completed = subprocess.run(
        [sys.executable, "-c", "import suitcode.runtime.main; print('ok')"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "ok"


def _patch_runtime(monkeypatch, project_root: Path, *, lsp_client_cls=_FakeRuntimeLspClient) -> None:
    monkeypatch.setattr(
        "suitcode.runtime.coordinator.detect_support_for_root",
        lambda root: type("Support", (), {"detected_providers": tuple()})(),
    )
    monkeypatch.setattr(
        "suitcode.runtime.coordinator.resolve_command_for_family",
        lambda family, attachment_root: (("fake-lsp",), {"family": family.value}),
    )
    monkeypatch.setattr(
        "suitcode.runtime.coordinator.LspClient",
        lsp_client_cls,
    )
    project_root.mkdir(parents=True, exist_ok=True)
