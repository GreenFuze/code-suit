from __future__ import annotations

import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.connection import Connection, Listener
from pathlib import Path

from suitcode.providers.registry import detect_support_for_root
from suitcode.providers.shared.lsp import LspClient, LspDocumentSymbol, LspLocation, LspWorkspaceSymbol
from suitcode.providers.shared.lsp.errors import LspTimeoutError
from suitcode.runtime.discovery import CoordinatorDiscoveryStore
from suitcode.runtime.endpoint import cleanup_endpoint, endpoint_uri_for_project, listen_on_endpoint
from suitcode.runtime.errors import (
    CoordinatorError,
    CoordinatorProtocolError,
    CoordinatorRequestTimeoutError,
    CoordinatorRuntimeNotReadyError,
    CoordinatorUnavailableError,
    CoordinatorVersionMismatchError,
)
from suitcode.runtime.lsp_payloads import (
    document_symbols_to_payload,
    locations_to_payload,
    workspace_symbols_to_payload,
)
from suitcode.runtime.models import (
    CoordinatorRequest,
    CoordinatorState,
    DefinitionRequest,
    DiscoveryRecord,
    DocumentSymbolPayload,
    DocumentSymbolRequest,
    EnsureServerReadyPayload,
    EnsureServerReadyRequest,
    ErrorPayload,
    GetRuntimeStatusRequest,
    HandshakePayload,
    HandshakeRequest,
    ImplementationRequest,
    LocationPayload,
    ManagedServerState,
    ManagedServerStatus,
    ReferencesRequest,
    ResponseEnvelope,
    RuntimeStatus,
    ServerFamily,
    ShutdownRequest,
    WorkspaceSymbolPayload,
    WorkspaceSymbolRequest,
)
from suitcode.runtime.paths import status_path_for_project
from suitcode.runtime.resolution import provider_id_to_server_family, resolve_command_for_family
from suitcode.runtime.transport import connect as connect_transport, receive_payload, send_payload
from suitcode.runtime.versioning import PROTOCOL_VERSION, build_version


_HEARTBEAT_INTERVAL_SECONDS = 5.0
_IDLE_MONITOR_INTERVAL_SECONDS = 5.0
_MAX_WARMUP_WORKERS = 2
_MAX_RETRY_BACKOFF_SECONDS = 60.0
_LSP_REQUEST_TIMEOUT_SECONDS = 10.0


def _request_from_payload(payload: dict[str, object]) -> CoordinatorRequest:
    kind = payload.get("kind")
    if kind == "handshake":
        return HandshakeRequest.model_validate(payload)
    if kind == "shutdown":
        return ShutdownRequest.model_validate(payload)
    if kind == "ensure_server_ready":
        return EnsureServerReadyRequest.model_validate(payload)
    if kind == "get_runtime_status":
        return GetRuntimeStatusRequest.model_validate(payload)
    if kind == "workspace_symbol":
        return WorkspaceSymbolRequest.model_validate(payload)
    if kind == "document_symbol":
        return DocumentSymbolRequest.model_validate(payload)
    if kind == "definition":
        return DefinitionRequest.model_validate(payload)
    if kind == "references":
        return ReferencesRequest.model_validate(payload)
    if kind == "implementation":
        return ImplementationRequest.model_validate(payload)
    raise CoordinatorProtocolError("coordinator request kind is missing or unsupported")


class _ManagedLspSession:
    def __init__(
        self,
        *,
        family: ServerFamily,
        attachment_root: Path,
        idle_ttl_seconds: float,
    ) -> None:
        self.family = family
        self.attachment_root = attachment_root.expanduser().resolve()
        self.idle_ttl_seconds = idle_ttl_seconds
        self.state = ManagedServerState.STOPPED
        self.last_activity_at: float | None = None
        self.last_failure_at: float | None = None
        self.next_retry_at: float | None = None
        self.failure_count = 0
        self._client: LspClient | None = None
        self._command: tuple[str, ...] | None = None
        self._init_options: dict[str, object] | None = None
        self._lock = threading.RLock()
        self._warmup_in_progress = False

    def status(self) -> ManagedServerStatus:
        with self._lock:
            return ManagedServerStatus(
                family=self.family,
                attachment_root=str(self.attachment_root),
                state=self.state,
                last_activity_at=self.last_activity_at,
                last_failure_at=self.last_failure_at,
                next_retry_at=self.next_retry_at,
                failure_count=self.failure_count,
            )

    def request_warmup(self) -> bool:
        now = time.time()
        with self._lock:
            if self._client is not None:
                self.last_activity_at = now
                self.state = ManagedServerState.READY
                return False
            if self._warmup_in_progress:
                return False
            if self.next_retry_at is not None and now < self.next_retry_at:
                self.state = ManagedServerState.DEGRADED
                return False
            self._warmup_in_progress = True
            self.state = ManagedServerState.WARMING
            self.last_activity_at = now
            return True

    def cancel_warmup_request(self) -> None:
        with self._lock:
            self._warmup_in_progress = False
            if self._client is None and self.state == ManagedServerState.WARMING:
                self.state = ManagedServerState.STOPPED

    def readiness_payload(self) -> EnsureServerReadyPayload:
        status = self.status()
        ready = status.state == ManagedServerState.READY
        retry_after_seconds: int | None = None
        if not ready:
            retry_after_seconds = self._retry_after_seconds(status)
        return EnsureServerReadyPayload(
            ready=ready,
            status=status,
            retry_after_seconds=retry_after_seconds,
            server_family=self.family,
            attachment_root=str(self.attachment_root),
        )

    def warm(self) -> None:
        try:
            self._ensure_ready(mark_warming=True)
        finally:
            with self._lock:
                self._warmup_in_progress = False
                if self._client is None and self.state == ManagedServerState.WARMING:
                    self.state = ManagedServerState.STOPPED

    def workspace_symbol(self, query: str) -> tuple[LspWorkspaceSymbol, ...]:
        return self._invoke(lambda client: client.workspace_symbol(query))

    def document_symbol(self, file_path: Path) -> tuple[LspDocumentSymbol, ...]:
        return self._invoke(lambda client: client.document_symbol(file_path))

    def definition(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return self._invoke(lambda client: client.definition(file_path, line, column))

    def references(
        self,
        file_path: Path,
        line: int,
        column: int,
        *,
        include_declaration: bool,
    ) -> tuple[LspLocation, ...]:
        return self._invoke(
            lambda client: client.references(
                file_path,
                line,
                column,
                include_declaration=include_declaration,
            )
        )

    def implementation(self, file_path: Path, line: int, column: int) -> tuple[LspLocation, ...]:
        return self._invoke(lambda client: client.implementation(file_path, line, column))

    def close_if_idle(self, now: float) -> None:
        with self._lock:
            if self._client is None or self.last_activity_at is None:
                return
            if now - self.last_activity_at < self.idle_ttl_seconds:
                return
            self._shutdown_locked()
            self.state = ManagedServerState.STOPPED

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown_locked()
            self.state = ManagedServerState.STOPPED

    def _invoke(self, operation):
        with self._lock:
            client = self._ensure_ready(mark_warming=False)
            try:
                result = operation(client)
            except LspTimeoutError as exc:
                self._mark_failure(exc)
                raise self._request_timeout_error() from exc
            except Exception as exc:  # noqa: BLE001
                self._mark_failure(exc)
                raise CoordinatorUnavailableError(
                    f"{self.family.value} request failed for attachment `{self.attachment_root}`: {exc}"
                ) from exc
            self.last_activity_at = time.time()
            self.state = ManagedServerState.READY
            return result

    def _ensure_ready(self, *, mark_warming: bool) -> LspClient:
        now = time.time()
        with self._lock:
            if self._client is not None and self.last_activity_at is not None:
                if now - self.last_activity_at >= self.idle_ttl_seconds:
                    self._shutdown_locked()
                    self.state = ManagedServerState.STOPPED
            if self.next_retry_at is not None and now < self.next_retry_at:
                raise self._degraded_retry_error()
            if self._client is not None:
                self.last_activity_at = now
                self.state = ManagedServerState.READY
                return self._client

            self.state = ManagedServerState.WARMING if mark_warming else ManagedServerState.STARTING
            try:
                command, initialization_options = resolve_command_for_family(self.family, self.attachment_root)
                client = LspClient(
                    command,
                    self.attachment_root,
                    initialization_options=initialization_options,
                    request_timeout_seconds=_LSP_REQUEST_TIMEOUT_SECONDS,
                )
                client.initialize(self.attachment_root)
            except LspTimeoutError as exc:
                self._mark_failure(exc)
                raise self._request_timeout_error() from exc
            except Exception as exc:  # noqa: BLE001
                self._mark_failure(exc)
                raise CoordinatorUnavailableError(
                    f"failed to start {self.family.value} for attachment `{self.attachment_root}`: {exc}"
                ) from exc

            self._client = client
            self._command = command
            self._init_options = initialization_options
            self.failure_count = 0
            self.next_retry_at = None
            self.last_failure_at = None
            self.last_activity_at = now
            self.state = ManagedServerState.READY
            return client

    def _mark_failure(self, exc: Exception) -> None:
        self.failure_count += 1
        self.last_failure_at = time.time()
        self.next_retry_at = self.last_failure_at + min(
            _MAX_RETRY_BACKOFF_SECONDS,
            float(2 ** min(self.failure_count, 6)),
        )
        self.state = ManagedServerState.DEGRADED
        self._shutdown_locked()

    @staticmethod
    def _retry_after_seconds(status: ManagedServerStatus) -> int:
        if status.state in {ManagedServerState.STARTING, ManagedServerState.WARMING, ManagedServerState.STOPPED}:
            return 15
        if status.state == ManagedServerState.DEGRADED and status.next_retry_at is not None:
            remaining = math.ceil(status.next_retry_at - time.time())
            return max(1, min(60, remaining))
        return 15

    def _request_timeout_error(self) -> CoordinatorRequestTimeoutError:
        status = self.status()
        return CoordinatorRequestTimeoutError(
            server_family=self.family,
            attachment_root=str(self.attachment_root),
            state=ManagedServerState.DEGRADED,
            retry_after_seconds=self._retry_after_seconds(status),
        )

    def _degraded_retry_error(self) -> CoordinatorRuntimeNotReadyError:
        status = self.status()
        return CoordinatorRuntimeNotReadyError(
            server_family=self.family,
            attachment_root=str(self.attachment_root),
            state=ManagedServerState.DEGRADED,
            retry_after_seconds=self._retry_after_seconds(status),
        )

    def _shutdown_locked(self) -> None:
        client = self._client
        self._client = None
        self._command = None
        self._init_options = None
        if client is None:
            return
        try:
            client.shutdown()
        except Exception:
            return


class CoordinatorServer:
    def __init__(
        self,
        *,
        project_root: Path,
        instance_id: str,
        idle_ttl_seconds: float = 60.0 * 60.0,
        managed_session_ttl_seconds: float = 60.0 * 60.0,
        warmup_concurrency: int = _MAX_WARMUP_WORKERS,
    ) -> None:
        self.project_root = project_root.expanduser().resolve()
        self.instance_id = instance_id
        self.protocol_version = PROTOCOL_VERSION
        self.build_version = build_version()
        self.idle_ttl_seconds = idle_ttl_seconds
        self.managed_session_ttl_seconds = managed_session_ttl_seconds
        self.warmup_concurrency = max(1, warmup_concurrency)
        self.started_at = time.time()
        self.last_activity_at = self.started_at
        self.last_heartbeat_at = self.started_at
        self.endpoint_transport_kind, self.endpoint_uri = endpoint_uri_for_project(self.project_root)
        self.status_path = status_path_for_project(self.project_root)
        self.status_store = CoordinatorDiscoveryStore(self.status_path)
        self._sessions: dict[tuple[ServerFamily, str], _ManagedLspSession] = {}
        self._sessions_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._listener: Listener | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._idle_thread: threading.Thread | None = None
        self._warmup_executor: ThreadPoolExecutor | None = None
        self._warmup_executor_lock = threading.RLock()
        self._warmup_futures = []
        self._active_requests = 0

    def run(self) -> None:
        self._listener = listen_on_endpoint(self.endpoint_uri)
        try:
            self._publish_discovery()
            if self._stop_event.is_set():
                return
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                name="suitcode-runtime-heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()
            self._idle_thread = threading.Thread(
                target=self._idle_monitor_loop,
                name="suitcode-runtime-idle",
                daemon=True,
            )
            self._idle_thread.start()
            self._schedule_warmups()
            self._serve()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            pass
        self._stop_event.set()
        self._poke_listener()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
        if self._warmup_executor is not None:
            self._warmup_executor.shutdown(wait=False, cancel_futures=True)
            self._warmup_executor = None
        with self._sessions_lock:
            for session in self._sessions.values():
                session.shutdown()
        self.status_store.remove_if_owned(self.instance_id)
        cleanup_endpoint(self.endpoint_uri)

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stop_event.is_set():
            try:
                connection = self._listener.accept()
            except (OSError, EOFError):
                if self._stop_event.is_set():
                    break
                continue
            if self._stop_event.is_set():
                try:
                    connection.close()
                except Exception:
                    pass
                break
            thread = threading.Thread(
                target=self._serve_connection,
                args=(connection,),
                name="suitcode-runtime-conn",
                daemon=True,
            )
            thread.start()

    def _serve_connection(self, connection: Connection) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    payload = receive_payload(connection)
                except CoordinatorUnavailableError:
                    return
                try:
                    request = _request_from_payload(payload)
                    with self._track_request():
                        response = self._dispatch(request)
                except CoordinatorError as exc:
                    response = ResponseEnvelope(
                        ok=False,
                        payload=exc.to_payload().model_dump(mode="json") if isinstance(exc, CoordinatorRuntimeNotReadyError) else None,
                        error=ErrorPayload(code=exc.__class__.__name__, message=str(exc)),
                    )
                except Exception as exc:  # noqa: BLE001
                    response = ResponseEnvelope(
                        ok=False,
                        error=ErrorPayload(code="InternalCoordinatorError", message=str(exc)),
                    )
                send_payload(connection, response.model_dump(mode="json"))
        finally:
            try:
                connection.close()
            except Exception:
                return

    def _dispatch(self, request: CoordinatorRequest) -> ResponseEnvelope:
        if isinstance(request, HandshakeRequest):
            if request.protocol_version != self.protocol_version or request.build_version != self.build_version:
                raise CoordinatorVersionMismatchError(
                    "coordinator version mismatch between thin client and runtime"
                )
            return ResponseEnvelope(
                ok=True,
                payload=HandshakePayload(
                    canonical_project_root=str(self.project_root),
                    instance_id=self.instance_id,
                    protocol_version=self.protocol_version,
                    build_version=self.build_version,
                    state=self._coordinator_state(),
                    started_at=self.started_at,
                    last_heartbeat_at=self.last_heartbeat_at,
                    expires_at=self._expires_at(),
                ).model_dump(mode="json"),
            )
        if isinstance(request, ShutdownRequest):
            self._stop_event.set()
            self._poke_listener()
            return ResponseEnvelope(ok=True, payload={"stopped": True})
        if isinstance(request, GetRuntimeStatusRequest):
            return ResponseEnvelope(ok=True, payload=self._runtime_status().model_dump(mode="json"))
        if isinstance(request, EnsureServerReadyRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            self._request_session_warmup(session)
            return ResponseEnvelope(
                ok=True,
                payload=session.readiness_payload().model_dump(mode="json"),
            )
        if isinstance(request, WorkspaceSymbolRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            payload = WorkspaceSymbolPayload(items=workspace_symbols_to_payload(session.workspace_symbol(request.query)))
            return ResponseEnvelope(ok=True, payload=payload.model_dump(mode="json"))
        if isinstance(request, DocumentSymbolRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            file_path = self._attachment_file_path(Path(request.attachment_root), request.repository_rel_path)
            payload = DocumentSymbolPayload(items=document_symbols_to_payload(session.document_symbol(file_path)))
            return ResponseEnvelope(ok=True, payload=payload.model_dump(mode="json"))
        if isinstance(request, DefinitionRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            file_path = self._attachment_file_path(Path(request.attachment_root), request.repository_rel_path)
            payload = LocationPayload(items=locations_to_payload(session.definition(file_path, request.line, request.column)))
            return ResponseEnvelope(ok=True, payload=payload.model_dump(mode="json"))
        if isinstance(request, ReferencesRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            file_path = self._attachment_file_path(Path(request.attachment_root), request.repository_rel_path)
            payload = LocationPayload(
                items=locations_to_payload(
                    session.references(
                        file_path,
                        request.line,
                        request.column,
                        include_declaration=request.include_declaration,
                    )
                )
            )
            return ResponseEnvelope(ok=True, payload=payload.model_dump(mode="json"))
        if isinstance(request, ImplementationRequest):
            session = self._ensure_session(request.family, Path(request.attachment_root))
            file_path = self._attachment_file_path(Path(request.attachment_root), request.repository_rel_path)
            payload = LocationPayload(items=locations_to_payload(session.implementation(file_path, request.line, request.column)))
            return ResponseEnvelope(ok=True, payload=payload.model_dump(mode="json"))
        raise CoordinatorProtocolError("unsupported coordinator request")

    def _runtime_status(self) -> RuntimeStatus:
        with self._sessions_lock:
            managed_servers = tuple(
                sorted(
                    (session.status() for session in self._sessions.values()),
                    key=lambda item: (item.family.value, item.attachment_root),
                )
            )
        return RuntimeStatus(
            canonical_project_root=str(self.project_root),
            instance_id=self.instance_id,
            protocol_version=self.protocol_version,
            build_version=self.build_version,
            state=self._coordinator_state(),
            started_at=self.started_at,
            last_heartbeat_at=self.last_heartbeat_at,
            expires_at=self._expires_at(),
            managed_servers=managed_servers,
        )

    def _coordinator_state(self) -> CoordinatorState:
        with self._sessions_lock:
            states = {session.state for session in self._sessions.values()}
        if self._stop_event.is_set():
            return CoordinatorState.SHUTTING_DOWN
        if not states:
            return CoordinatorState.STARTING if time.time() - self.started_at < _HEARTBEAT_INTERVAL_SECONDS else CoordinatorState.READY
        if ManagedServerState.WARMING in states or ManagedServerState.STARTING in states:
            return CoordinatorState.WARMING
        if ManagedServerState.DEGRADED in states:
            return CoordinatorState.DEGRADED
        return CoordinatorState.READY

    def _expires_at(self) -> float:
        return self.last_activity_at + self.idle_ttl_seconds

    def _publish_discovery(self) -> None:
        self.last_heartbeat_at = time.time()
        self.status_store.write(
            DiscoveryRecord(
                canonical_project_root=str(self.project_root),
                endpoint=self.endpoint_uri,
                transport_kind=self.endpoint_transport_kind,
                pid=os.getpid(),
                protocol_version=self.protocol_version,
                build_version=self.build_version,
                instance_id=self.instance_id,
                started_at=self.started_at,
                last_heartbeat_at=self.last_heartbeat_at,
                expires_at=self._expires_at(),
                state=self._coordinator_state(),
            )
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            self._publish_discovery()

    def _idle_monitor_loop(self) -> None:
        while not self._stop_event.wait(_IDLE_MONITOR_INTERVAL_SECONDS):
            now = time.time()
            with self._sessions_lock:
                for session in self._sessions.values():
                    session.close_if_idle(now)
            with self._state_lock:
                active = self._active_requests
            if active == 0 and now >= self._expires_at():
                self._stop_event.set()
                self._poke_listener()
                if self._listener is not None:
                    try:
                        self._listener.close()
                    except Exception:
                        pass
                break

    def _schedule_warmups(self) -> None:
        families: list[tuple[ServerFamily, Path]] = []
        support = detect_support_for_root(self.project_root)
        for detected in support.detected_providers:
            family = provider_id_to_server_family(detected.provider_id)
            if family is None:
                continue
            for attachment in detected.attachments:
                families.append((family, attachment.attachment_root))
        if not families:
            return
        for family, attachment_root in families:
            self._request_session_warmup(self._ensure_session(family, attachment_root))

    def _warm_session(self, session: _ManagedLspSession) -> None:
        try:
            session.warm()
        except CoordinatorError:
            return

    def _request_session_warmup(self, session: _ManagedLspSession) -> None:
        if not session.request_warmup():
            return
        try:
            future = self._warmup_executor_instance().submit(self._warm_session, session)
        except Exception:
            session.cancel_warmup_request()
            raise
        self._warmup_futures.append(future)

    def _warmup_executor_instance(self) -> ThreadPoolExecutor:
        with self._warmup_executor_lock:
            if self._warmup_executor is None:
                self._warmup_executor = ThreadPoolExecutor(
                    max_workers=self.warmup_concurrency,
                    thread_name_prefix="suitcode-runtime-warmup",
                )
            return self._warmup_executor

    def _ensure_session(self, family: ServerFamily, attachment_root: Path) -> _ManagedLspSession:
        normalized_attachment = attachment_root.expanduser().resolve()
        key = (family, str(normalized_attachment))
        with self._sessions_lock:
            session = self._sessions.get(key)
            if session is None:
                session = _ManagedLspSession(
                    family=family,
                    attachment_root=normalized_attachment,
                    idle_ttl_seconds=self.managed_session_ttl_seconds,
                )
                self._sessions[key] = session
            return session

    def _poke_listener(self) -> None:
        try:
            connection = connect_transport(self.endpoint_uri)
        except CoordinatorUnavailableError:
            return
        connection.close()

    def _attachment_file_path(self, attachment_root: Path, repository_rel_path: str) -> Path:
        normalized_root = attachment_root.expanduser().resolve()
        normalized_path = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
        if not normalized_path:
            raise CoordinatorProtocolError("repository_rel_path must not be empty")
        file_path = (normalized_root / normalized_path).resolve()
        try:
            file_path.relative_to(normalized_root)
        except ValueError as exc:
            raise CoordinatorProtocolError("repository_rel_path escapes attachment root") from exc
        return file_path

    def _track_request(self):
        server = self

        class _RequestScope:
            def __enter__(self_inner):
                with server._state_lock:
                    server._active_requests += 1
                    server.last_activity_at = time.time()
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                with server._state_lock:
                    server._active_requests = max(0, server._active_requests - 1)
                    server.last_activity_at = time.time()
                return False

        return _RequestScope()
