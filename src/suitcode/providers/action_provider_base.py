from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.action_models import RepositoryAction
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.provider_metadata import ProviderAttachmentContext
from suitcode.providers.runtime_capability_models import ActionRuntimeCapabilities

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ActionProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository, attachment: ProviderAttachmentContext) -> None:
        super().__init__(repository, attachment)

    @abstractmethod
    def get_actions(self) -> tuple[RepositoryAction, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_action_runtime_capabilities(self) -> ActionRuntimeCapabilities:
        raise NotImplementedError
