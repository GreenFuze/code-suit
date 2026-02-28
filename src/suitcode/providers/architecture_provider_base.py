from __future__ import annotations

from abc import ABC, abstractmethod

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition,
)
from suitcode.core.repository import Repository


class ArchitectureProviderBase(ABC):
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    @property
    def repository(self) -> Repository:
        return self._repository

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
    def get_tests(self) -> tuple[TestDefinition, ...]:
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
