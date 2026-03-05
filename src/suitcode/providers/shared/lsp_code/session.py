from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Protocol

from suitcode.providers.shared.lsp import LspClient


LspClientFactory = Callable[..., LspClient]


class LspResolver(Protocol):
    def resolve(self, repository_root: Path) -> tuple[str, ...]:
        raise NotImplementedError


class LspSessionManager(Protocol):
    def open_client(
        self,
        repository_root: Path,
        resolver: LspResolver,
        client_factory: LspClientFactory,
    ) -> ContextManager[LspClient]:
        raise NotImplementedError


class PerCallLspSessionManager:
    @contextmanager
    def open_client(
        self,
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
