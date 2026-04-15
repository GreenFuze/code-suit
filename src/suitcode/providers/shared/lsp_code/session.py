from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Protocol

from suitcode.providers.shared.lsp import LspClient
from suitcode.runtime.client import ProjectCoordinatorClient
from suitcode.runtime.errors import CoordinatorRuntimeNotReadyError
from suitcode.runtime.lsp_payloads import (
    document_symbols_from_payload,
    locations_from_payload,
    workspace_symbols_from_payload,
)
from suitcode.runtime.models import (
    DocumentSymbolPayload,
    DocumentSymbolRequest,
    DefinitionRequest,
    ImplementationRequest,
    ReferencesRequest,
    ServerFamily,
    WorkspaceSymbolPayload,
    WorkspaceSymbolRequest,
    LocationPayload,
)
from suitcode.runtime.resolution import server_family_for_resolver


LspClientFactory = Callable[..., LspClient]


class LspResolver(Protocol):
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        raise NotImplementedError


class LspSessionManager(Protocol):
    def open_client(
        self,
        project_root: Path,
        repository_root: Path,
        resolver: LspResolver,
        client_factory: LspClientFactory,
    ) -> ContextManager[LspClient]:
        raise NotImplementedError


class PerCallLspSessionManager:
    @contextmanager
    def open_client(
        self,
        project_root: Path,
        repository_root: Path,
        resolver: LspResolver,
        client_factory: LspClientFactory,
    ):
        root = repository_root.expanduser().resolve()
        command = resolver.resolve(root)
        initialization_options = (
            resolver.resolve_initialization_options(root)
            if hasattr(resolver, "resolve_initialization_options")
            else None
        )
        try:
            client = client_factory(command, root, initialization_options)
        except TypeError:
            client = client_factory(command, root)
        try:
            yield client
        finally:
            close = getattr(client, "shutdown", None)
            if callable(close):
                close()


class CoordinatorBackedLspSessionManager:
    def __init__(self, *, fallback_manager: PerCallLspSessionManager | None = None) -> None:
        self._fallback_manager = fallback_manager or PerCallLspSessionManager()

    @contextmanager
    def open_client(
        self,
        project_root: Path,
        repository_root: Path,
        resolver: LspResolver,
        client_factory: LspClientFactory,
    ):
        family = server_family_for_resolver(resolver)
        if family is None:
            with self._fallback_manager.open_client(project_root, repository_root, resolver, client_factory) as client:
                yield client
            return

        normalized_project_root = project_root.expanduser().resolve()
        normalized_attachment_root = repository_root.expanduser().resolve()
        coordinator = ProjectCoordinatorClient(normalized_project_root)
        readiness = coordinator.ensure_server_ready(family, normalized_attachment_root)
        if not readiness.ready:
            raise CoordinatorRuntimeNotReadyError(
                server_family=readiness.server_family,
                attachment_root=readiness.attachment_root,
                state=readiness.status.state,
                retry_after_seconds=readiness.retry_after_seconds or 15,
            )
        with coordinator.open_connection() as connection:
            yield _CoordinatorLspClient(
                connection=connection,
                family=family,
                attachment_root=normalized_attachment_root,
            )


class _CoordinatorLspClient:
    def __init__(self, *, connection, family: ServerFamily, attachment_root: Path) -> None:
        self._connection = connection
        self._family = family
        self._attachment_root = attachment_root

    def initialize(self, root_path: Path) -> None:  # noqa: ARG002
        return None

    def workspace_symbol(self, query: str):
        payload = self._connection.request(
            WorkspaceSymbolRequest(
                family=self._family,
                attachment_root=str(self._attachment_root),
                query=query,
            )
        )
        if payload is None:
            raise ValueError("coordinator workspace_symbol response is missing a payload")
        return workspace_symbols_from_payload(WorkspaceSymbolPayload.model_validate(payload).items)

    def document_symbol(self, file_path: Path):
        payload = self._connection.request(
            DocumentSymbolRequest(
                family=self._family,
                attachment_root=str(self._attachment_root),
                repository_rel_path=self._repository_rel_path(file_path),
            )
        )
        if payload is None:
            raise ValueError("coordinator document_symbol response is missing a payload")
        return document_symbols_from_payload(DocumentSymbolPayload.model_validate(payload).items)

    def definition(self, file_path: Path, line: int, column: int):
        payload = self._connection.request(
            DefinitionRequest(
                family=self._family,
                attachment_root=str(self._attachment_root),
                repository_rel_path=self._repository_rel_path(file_path),
                line=line,
                column=column,
            )
        )
        if payload is None:
            raise ValueError("coordinator definition response is missing a payload")
        return locations_from_payload(LocationPayload.model_validate(payload).items)

    def references(self, file_path: Path, line: int, column: int, include_declaration: bool = False):
        payload = self._connection.request(
            ReferencesRequest(
                family=self._family,
                attachment_root=str(self._attachment_root),
                repository_rel_path=self._repository_rel_path(file_path),
                line=line,
                column=column,
                include_declaration=include_declaration,
            )
        )
        if payload is None:
            raise ValueError("coordinator references response is missing a payload")
        return locations_from_payload(LocationPayload.model_validate(payload).items)

    def implementation(self, file_path: Path, line: int, column: int):
        payload = self._connection.request(
            ImplementationRequest(
                family=self._family,
                attachment_root=str(self._attachment_root),
                repository_rel_path=self._repository_rel_path(file_path),
                line=line,
                column=column,
            )
        )
        if payload is None:
            raise ValueError("coordinator implementation response is missing a payload")
        return locations_from_payload(LocationPayload.model_validate(payload).items)

    def shutdown(self) -> None:
        return None

    def _repository_rel_path(self, file_path: Path) -> str:
        resolved = file_path.expanduser().resolve()
        return resolved.relative_to(self._attachment_root).as_posix()
