from __future__ import annotations

from abc import ABC

from suitcode.core.repository import Repository


class ProviderBase(ABC):
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    @property
    def repository(self) -> Repository:
        return self._repository
