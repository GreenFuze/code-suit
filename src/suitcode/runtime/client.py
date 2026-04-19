from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from multiprocessing.connection import Connection
from pathlib import Path

from suitcode.runtime.discovery import CoordinatorDiscoveryStore
from suitcode.runtime.endpoint import endpoint_uri_for_project
from suitcode.runtime.errors import (
    CoordinatorElectionError,
    CoordinatorProtocolError,
    CoordinatorRuntimeNotReadyError,
    CoordinatorUnavailableError,
    CoordinatorVersionMismatchError,
)
from suitcode.runtime.lockfile import project_lock
from suitcode.runtime.models import (
    CoordinatorState,
    EnsureServerReadyPayload,
    EnsureServerReadyRequest,
    GetRuntimeStatusRequest,
    HandshakePayload,
    HandshakeRequest,
    ManagedServerState,
    ResponseEnvelope,
    RuntimeStatus,
    ServerFamily,
    ShutdownRequest,
)
from suitcode.runtime.paths import status_path_for_project
from suitcode.runtime.process import is_process_running, terminate_process
from suitcode.runtime.transport import connect, receive_payload, send_payload
from suitcode.runtime.versioning import PROTOCOL_VERSION, build_version


_BOOTSTRAP_TIMEOUT_SECONDS: float | None = None
_CONNECT_RETRY_ATTEMPTS = 10
_CONNECT_RETRY_DELAY_SECONDS = 0.1


def _prepend_pythonpath_entry(existing: str | None, entry: str) -> str:
    normalized_entry = entry.strip()
    if not normalized_entry:
        return existing or ""
    if not existing:
        return normalized_entry
    parts = [part for part in existing.split(os.pathsep) if part]
    normalized_existing = {os.path.normcase(part) for part in parts}
    if os.path.normcase(normalized_entry) in normalized_existing:
        return existing
    return os.pathsep.join((normalized_entry, existing))


class CoordinatorRpcConnection:
    def __init__(self, *, project_root: Path, endpoint_uri: str, connection: Connection) -> None:
        self.project_root = project_root
        self.endpoint_uri = endpoint_uri
        self._connection = connection

    def request(self, request) -> dict[str, object] | None:
        send_payload(self._connection, request.model_dump(mode="json"))
        raw_response = receive_payload(self._connection)
        envelope = ResponseEnvelope.model_validate(raw_response)
        if not envelope.ok:
            if envelope.error is None:
                raise CoordinatorProtocolError("coordinator returned an error response without an error payload")
            if envelope.error.code == "CoordinatorVersionMismatchError":
                raise CoordinatorVersionMismatchError(envelope.error.message)
            if envelope.error.code == "CoordinatorProtocolError":
                raise CoordinatorProtocolError(envelope.error.message)
            if envelope.error.code in {"CoordinatorRuntimeNotReadyError", "CoordinatorRequestTimeoutError"}:
                payload = envelope.payload or {}
                try:
                    readiness = EnsureServerReadyPayload.model_validate(payload)
                except Exception as exc:  # noqa: BLE001
                    raise CoordinatorProtocolError(
                        "coordinator returned a runtime-not-ready error without a valid readiness payload"
                    ) from exc
                raise CoordinatorRuntimeNotReadyError(
                    server_family=readiness.server_family,
                    attachment_root=readiness.attachment_root,
                    state=readiness.status.state,
                    retry_after_seconds=readiness.retry_after_seconds or 15,
                )
            raise CoordinatorUnavailableError(envelope.error.message)
        return envelope.payload

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception:
            return


class ProjectCoordinatorClient:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.status_path = status_path_for_project(self.project_root)
        self.status_store = CoordinatorDiscoveryStore(self.status_path)
        self.endpoint_transport_kind, self.endpoint_uri = endpoint_uri_for_project(self.project_root)
        self.protocol_version = PROTOCOL_VERSION
        self.build_version = build_version()

    @contextmanager
    def open_connection(self):
        self._ensure_coordinator()
        connection = self._connect_to_coordinator_with_retries(self.endpoint_uri)
        try:
            yield connection
        finally:
            connection.close()

    def get_runtime_status(self) -> RuntimeStatus:
        with self.open_connection() as connection:
            payload = connection.request(GetRuntimeStatusRequest())
            if payload is None:
                raise CoordinatorProtocolError("runtime status response is missing a payload")
            return RuntimeStatus.model_validate(payload)

    def ensure_server_ready(self, family: ServerFamily, attachment_root: Path) -> EnsureServerReadyPayload:
        with self.open_connection() as connection:
            payload = connection.request(
                EnsureServerReadyRequest(
                    family=family,
                    attachment_root=str(attachment_root.expanduser().resolve()),
                )
            )
            if payload is None:
                raise CoordinatorProtocolError("ensure_server_ready response is missing a payload")
            return EnsureServerReadyPayload.model_validate(payload)

    def wait_until_server_ready(
        self,
        family: ServerFamily,
        attachment_root: Path,
        *,
        timeout_seconds: float | None = None,
        poll_interval_seconds: float = 0.5,
    ) -> EnsureServerReadyPayload:
        normalized_attachment_root = attachment_root.expanduser().resolve()
        deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
        last_payload: EnsureServerReadyPayload | None = None
        while True:
            last_payload = self.ensure_server_ready(family, normalized_attachment_root)
            if last_payload.ready:
                return last_payload
            retry_after = float(max(0, last_payload.retry_after_seconds or 0))
            sleep_seconds = max(poll_interval_seconds, retry_after)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return last_payload
                sleep_seconds = min(sleep_seconds, remaining)
            time.sleep(sleep_seconds)

    def wait_for_project_warmup(
        self,
        *,
        timeout_seconds: float | None = 90.0,
        poll_interval_seconds: float = 0.5,
    ) -> RuntimeStatus | None:
        expected_sessions = self._expected_project_sessions()
        if not expected_sessions:
            return None

        deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
        for family, attachment_root in sorted(expected_sessions, key=lambda item: (item[0].value, item[1])):
            remaining_timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            readiness = self.wait_until_server_ready(
                family,
                Path(attachment_root),
                timeout_seconds=remaining_timeout,
                poll_interval_seconds=poll_interval_seconds,
            )
            if not readiness.ready:
                return self.get_runtime_status()
        return self.get_runtime_status()

    def shutdown(self) -> None:
        record = self._current_status_record()
        endpoint_uri = self.endpoint_uri if record is None else record.endpoint
        try:
            connection = self._connect_to_coordinator_with_retries(endpoint_uri, attempts=2)
        except CoordinatorUnavailableError:
            if record is not None and not is_process_running(record.pid):
                self.status_store.remove_if_owned(record.instance_id)
                return
            if record is None:
                return
            raise
        try:
            connection.request(ShutdownRequest())
        finally:
            connection.close()

    def _expected_project_sessions(self) -> set[tuple[ServerFamily, str]]:
        from suitcode.providers.registry import detect_support_for_root
        from suitcode.runtime.resolution import provider_id_to_server_family

        support = detect_support_for_root(self.project_root)
        expected: set[tuple[ServerFamily, str]] = set()
        for detected_provider in support.detected_providers:
            family = provider_id_to_server_family(detected_provider.provider_id)
            if family is None:
                continue
            for attachment in detected_provider.attachments:
                expected.add((family, str(attachment.attachment_root.expanduser().resolve())))
        return expected

    @staticmethod
    def _warmup_has_settled(
        status: RuntimeStatus,
        expected_sessions: set[tuple[ServerFamily, str]],
    ) -> bool:
        if status.state == CoordinatorState.SHUTTING_DOWN:
            return False
        managed_by_key = {
            (managed.family, managed.attachment_root): managed
            for managed in status.managed_servers
        }
        for key in expected_sessions:
            managed = managed_by_key.get(key)
            if managed is None:
                return False
            if managed.state != ManagedServerState.READY:
                return False
        return True

    def _ensure_coordinator(self) -> None:
        last_error = self._probe_existing_coordinator()
        if last_error is None:
            return
        instance_id = uuid.uuid4().hex
        with project_lock(self.project_root, instance_id):
            last_error = self._probe_existing_coordinator()
            if last_error is None:
                return
            self._replace_or_cleanup_locked(last_error)
            candidate_process = self._spawn_candidate(instance_id)
            self._wait_for_coordinator(candidate_process)

    def _probe_existing_coordinator(self) -> Exception | None:
        record = self._current_status_record()
        endpoint_uri = self.endpoint_uri if record is None else record.endpoint
        try:
            connection = self._connect_to_coordinator_with_retries(endpoint_uri, attempts=2)
        except (CoordinatorUnavailableError, CoordinatorVersionMismatchError) as exc:
            return exc
        connection.close()
        return None

    def _current_status_record(self):
        record = self.status_store.read()
        if record is None:
            return None
        if record.expires_at <= time.time():
            return None
        if not is_process_running(record.pid):
            return None
        return record

    def _replace_or_cleanup_locked(self, last_error: Exception) -> None:
        record = self.status_store.read()
        if record is None:
            return
        if record.protocol_version != self.protocol_version or record.build_version != self.build_version:
            terminate_process(record.pid)
            self.status_store.remove_if_owned(record.instance_id)
            return
        if not is_process_running(record.pid) or record.expires_at <= time.time():
            self.status_store.remove_if_owned(record.instance_id)
            return
        if isinstance(last_error, CoordinatorVersionMismatchError):
            terminate_process(record.pid)
            self.status_store.remove_if_owned(record.instance_id)
            return
        terminate_process(record.pid)
        self.status_store.remove_if_owned(record.instance_id)

    def _spawn_candidate(self, instance_id: str) -> None:
        source_root = Path(__file__).resolve().parents[2]
        command = [
            sys.executable,
            "-m",
            "suitcode.runtime.main",
            "--project-root",
            str(self.project_root),
            "--instance-id",
            instance_id,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = _prepend_pythonpath_entry(env.get("PYTHONPATH"), str(source_root))
        kwargs: dict[str, object] = {
            "cwd": str(self.project_root),
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            if creationflags:
                kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(command, **kwargs)

    def _wait_for_coordinator(self, candidate_process=None) -> None:
        deadline = None if _BOOTSTRAP_TIMEOUT_SECONDS is None else time.time() + _BOOTSTRAP_TIMEOUT_SECONDS
        last_error: Exception | None = None
        while deadline is None or time.time() < deadline:
            try:
                connection = self._connect_to_coordinator(self.endpoint_uri)
            except (CoordinatorUnavailableError, CoordinatorVersionMismatchError) as exc:
                last_error = exc
                if candidate_process is not None:
                    return_code = candidate_process.poll()
                    if return_code is not None:
                        raise CoordinatorUnavailableError(
                            "coordinator process exited before binding the project endpoint "
                            f"for `{self.project_root}` (exit code {return_code}). "
                            "Ensure the current SuitCode source/install is importable to child Python processes."
                        ) from exc
                time.sleep(0.1)
                continue
            connection.close()
            return
        if deadline is not None and last_error is not None:
            raise CoordinatorUnavailableError(
                f"timed out waiting for coordinator startup for `{self.project_root}`: {last_error}"
            ) from last_error
        if deadline is not None:
            raise CoordinatorElectionError(
                f"timed out waiting for coordinator startup to settle for `{self.project_root}`"
            )
        raise CoordinatorUnavailableError(
            f"unable to wait for coordinator startup for `{self.project_root}`"
        )

    def _connect_to_coordinator(self, endpoint_uri: str) -> CoordinatorRpcConnection:
        raw_connection = connect(endpoint_uri)
        connection = CoordinatorRpcConnection(
            project_root=self.project_root,
            endpoint_uri=endpoint_uri,
            connection=raw_connection,
        )
        payload = connection.request(
            HandshakeRequest(
                protocol_version=self.protocol_version,
                build_version=self.build_version,
            )
        )
        if payload is None:
            connection.close()
            raise CoordinatorProtocolError("coordinator handshake response is missing a payload")
        handshake = HandshakePayload.model_validate(payload)
        if Path(handshake.canonical_project_root).resolve() != self.project_root:
            connection.close()
            raise CoordinatorProtocolError("coordinator handshake returned a mismatched project root")
        return connection

    def _connect_to_coordinator_with_retries(
        self,
        endpoint_uri: str,
        *,
        attempts: int = _CONNECT_RETRY_ATTEMPTS,
    ) -> CoordinatorRpcConnection:
        last_error: CoordinatorUnavailableError | None = None
        for attempt in range(max(1, attempts)):
            try:
                return self._connect_to_coordinator(endpoint_uri)
            except CoordinatorUnavailableError as exc:
                last_error = exc
                if attempt == max(1, attempts) - 1:
                    raise
                time.sleep(_CONNECT_RETRY_DELAY_SECONDS)
        if last_error is not None:
            raise last_error
        raise CoordinatorUnavailableError(f"unable to connect to coordinator endpoint `{endpoint_uri}`")
