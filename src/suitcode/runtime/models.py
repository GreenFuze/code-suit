from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransportKind(StrEnum):
    PIPE = "pipe"
    UNIX = "unix"


class ServerFamily(StrEnum):
    GOPLS = "gopls"
    BASEDPYRIGHT = "basedpyright"
    TYPESCRIPT_LANGUAGE_SERVER = "typescript-language-server"


class CoordinatorState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    WARMING = "warming"
    DEGRADED = "degraded"
    SHUTTING_DOWN = "shutting_down"


class ManagedServerState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    WARMING = "warming"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class DiscoveryRecord(RuntimeModel):
    canonical_project_root: str
    endpoint: str
    transport_kind: TransportKind
    pid: int
    protocol_version: str
    build_version: str
    instance_id: str
    started_at: float
    last_heartbeat_at: float
    expires_at: float
    state: CoordinatorState


class LockRecord(RuntimeModel):
    pid: int
    instance_id: str
    acquired_at: float


class ManagedServerStatus(RuntimeModel):
    family: ServerFamily
    attachment_root: str
    state: ManagedServerState
    last_activity_at: float | None = None
    last_failure_at: float | None = None
    next_retry_at: float | None = None
    failure_count: int = 0


class RuntimeStatus(RuntimeModel):
    canonical_project_root: str
    instance_id: str
    protocol_version: str
    build_version: str
    state: CoordinatorState
    started_at: float
    last_heartbeat_at: float
    expires_at: float
    managed_servers: tuple[ManagedServerStatus, ...] = Field(default_factory=tuple)


class HandshakeRequest(RuntimeModel):
    kind: Literal["handshake"] = "handshake"
    protocol_version: str
    build_version: str


class ShutdownRequest(RuntimeModel):
    kind: Literal["shutdown"] = "shutdown"


class EnsureServerReadyRequest(RuntimeModel):
    kind: Literal["ensure_server_ready"] = "ensure_server_ready"
    family: ServerFamily
    attachment_root: str


class GetRuntimeStatusRequest(RuntimeModel):
    kind: Literal["get_runtime_status"] = "get_runtime_status"


class WorkspaceSymbolRequest(RuntimeModel):
    kind: Literal["workspace_symbol"] = "workspace_symbol"
    family: ServerFamily
    attachment_root: str
    query: str


class DocumentSymbolRequest(RuntimeModel):
    kind: Literal["document_symbol"] = "document_symbol"
    family: ServerFamily
    attachment_root: str
    repository_rel_path: str


class DefinitionRequest(RuntimeModel):
    kind: Literal["definition"] = "definition"
    family: ServerFamily
    attachment_root: str
    repository_rel_path: str
    line: int
    column: int


class ReferencesRequest(RuntimeModel):
    kind: Literal["references"] = "references"
    family: ServerFamily
    attachment_root: str
    repository_rel_path: str
    line: int
    column: int
    include_declaration: bool = False


class ImplementationRequest(RuntimeModel):
    kind: Literal["implementation"] = "implementation"
    family: ServerFamily
    attachment_root: str
    repository_rel_path: str
    line: int
    column: int


CoordinatorRequest = (
    HandshakeRequest
    | ShutdownRequest
    | EnsureServerReadyRequest
    | GetRuntimeStatusRequest
    | WorkspaceSymbolRequest
    | DocumentSymbolRequest
    | DefinitionRequest
    | ReferencesRequest
    | ImplementationRequest
)


class ErrorPayload(RuntimeModel):
    code: str
    message: str


class HandshakePayload(RuntimeModel):
    canonical_project_root: str
    instance_id: str
    protocol_version: str
    build_version: str
    state: CoordinatorState
    started_at: float
    last_heartbeat_at: float
    expires_at: float


class EnsureServerReadyPayload(RuntimeModel):
    ready: bool
    status: ManagedServerStatus
    retry_after_seconds: int | None = None
    server_family: ServerFamily
    attachment_root: str


class WorkspaceSymbolPayload(RuntimeModel):
    items: tuple[dict[str, object], ...] = Field(default_factory=tuple)


class DocumentSymbolPayload(RuntimeModel):
    items: tuple[dict[str, object], ...] = Field(default_factory=tuple)


class LocationPayload(RuntimeModel):
    items: tuple[dict[str, object], ...] = Field(default_factory=tuple)


class ResponseEnvelope(RuntimeModel):
    ok: bool
    payload: dict[str, object] | None = None
    error: ErrorPayload | None = None


class RequestEnvelope(RuntimeModel):
    payload: dict[str, object]
