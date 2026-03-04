from __future__ import annotations

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
)
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.provider_roles import ProviderRole


class ArchitectureIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[ArchitectureProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_role(ProviderRole.ARCHITECTURE)
            if isinstance(provider, ArchitectureProviderBase)
        )

    def get_components(self) -> tuple[Component, ...]:
        return self._collect(lambda provider: provider.get_components())

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return self._collect(lambda provider: provider.get_aggregators())

    def get_runners(self) -> tuple[Runner, ...]:
        return self._collect(lambda provider: provider.get_runners())

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return self._collect(lambda provider: provider.get_package_managers())

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return self._collect(lambda provider: provider.get_external_packages())

    def get_files(self) -> tuple[FileInfo, ...]:
        return self._collect(lambda provider: provider.get_files())

    def _collect(self, getter):
        items = [item for provider in self.providers for item in getter(provider)]
        return tuple(sorted(items, key=lambda item: item.id))


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
