from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.quality_models import QualityFileResult

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class QualityProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        raise NotImplementedError

    @abstractmethod
    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        raise NotImplementedError
