from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.code.models import CodeLocation
from suitcode.core.models import EntityInfo
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.runtime_capability_models import CodeRuntimeCapabilities

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class CodeProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def get_symbol(self, query: str, is_case_sensitive: bool = False) -> tuple[EntityInfo, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        raise NotImplementedError

    @abstractmethod
    def find_definition(self, repository_rel_path: str, line: int, column: int) -> tuple[CodeLocation, ...]:
        raise NotImplementedError

    @abstractmethod
    def find_references(
        self,
        repository_rel_path: str,
        line: int,
        column: int,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_code_runtime_capabilities(self) -> CodeRuntimeCapabilities:
        raise NotImplementedError
