from __future__ import annotations

from abc import ABC, abstractmethod

from suitcode.core.models import EntityInfo
from suitcode.core.repository import Repository
from suitcode.providers.provider_base import ProviderBase


class CodeProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def get_symbol(self, query: str) -> tuple[EntityInfo, ...]:
        raise NotImplementedError
