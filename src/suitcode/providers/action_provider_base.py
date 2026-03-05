from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.action_models import RepositoryAction
from suitcode.providers.provider_base import ProviderBase

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ActionProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def get_actions(self) -> tuple[RepositoryAction, ...]:
        raise NotImplementedError
