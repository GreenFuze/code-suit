from __future__ import annotations

from suitcode.runtime.models import EnsureServerReadyPayload, ManagedServerState, ManagedServerStatus, ServerFamily


class CoordinatorError(RuntimeError):
    """Base coordinator/runtime error."""


class CoordinatorProtocolError(CoordinatorError):
    """Raised when the coordinator protocol payload is invalid."""


class CoordinatorUnavailableError(CoordinatorError):
    """Raised when the coordinator or one of its managed servers is unavailable."""


class CoordinatorVersionMismatchError(CoordinatorError):
    """Raised when coordinator protocol/build versions do not match the client."""


class CoordinatorElectionError(CoordinatorError):
    """Raised when bootstrap/election flow cannot determine a winner."""


class CoordinatorRuntimeNotReadyError(CoordinatorUnavailableError):
    """Raised when a managed runtime is warming or backoff-limited."""

    def __init__(
        self,
        *,
        server_family: ServerFamily,
        attachment_root: str,
        state: ManagedServerState,
        retry_after_seconds: int,
    ) -> None:
        self.server_family = server_family
        self.attachment_root = attachment_root
        self.state = state
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{server_family.value} is {state.value} for attachment `{attachment_root}`; "
            f"retry after {retry_after_seconds}s"
        )

    def to_payload(self) -> EnsureServerReadyPayload:
        return EnsureServerReadyPayload(
            ready=False,
            status=ManagedServerStatus(
                family=self.server_family,
                attachment_root=self.attachment_root,
                state=self.state,
            ),
            retry_after_seconds=self.retry_after_seconds,
            server_family=self.server_family,
            attachment_root=self.attachment_root,
        )


class CoordinatorRequestTimeoutError(CoordinatorRuntimeNotReadyError):
    """Raised when a semantic LSP request timed out and the session was degraded."""


class SemanticQueryTimeoutError(RuntimeError):
    def __init__(
        self,
        *,
        server_name: str,
        attachment_root: str,
        retry_after_seconds: int = 15,
        state: str = "degraded",
    ) -> None:
        self.server_name = server_name
        self.attachment_root = attachment_root
        self.retry_after_seconds = retry_after_seconds
        self.state = state
        super().__init__(
            f"{server_name} semantic query budget exceeded for attachment `{attachment_root}`; "
            f"retry after {retry_after_seconds}s"
        )
