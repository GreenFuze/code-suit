from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
)
from suitcode.core.intelligence_models import DependencyRef
from suitcode.providers.provider_base import ProviderBase

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ArchitectureProviderBase(ProviderBase, ABC):
    def __init__(self, repository: Repository) -> None:
        super().__init__(repository)

    @abstractmethod
    def get_components(self) -> tuple[Component, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_aggregators(self) -> tuple[Aggregator, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_runners(self) -> tuple[Runner, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_package_managers(self) -> tuple[PackageManager, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_files(self) -> tuple[FileInfo, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_component_dependencies(self, component_id: str) -> tuple[DependencyRef, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_component_dependents(self, component_id: str) -> tuple[str, ...]:
        raise NotImplementedError
