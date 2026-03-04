from __future__ import annotations

from suitcode.core.intelligence_models import DependencyRef
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
        self._component_provider_index: dict[str, ArchitectureProviderBase] | None = None

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

    def get_component_dependencies(self, component_id: str) -> tuple[DependencyRef, ...]:
        provider = self._provider_for_component_id(component_id)
        return tuple(
            sorted(
                provider.get_component_dependencies(component_id),
                key=lambda item: (item.target_kind, item.target_id, item.dependency_scope),
            )
        )

    def get_component_dependents(self, component_id: str) -> tuple[str, ...]:
        provider = self._provider_for_component_id(component_id)
        return tuple(sorted(provider.get_component_dependents(component_id)))

    def _collect(self, getter):
        items = [item for provider in self.providers for item in getter(provider)]
        return tuple(sorted(items, key=lambda item: item.id))

    def _provider_for_component_id(self, component_id: str) -> ArchitectureProviderBase:
        if self._component_provider_index is None:
            index: dict[str, ArchitectureProviderBase] = {}
            for provider in self.providers:
                for component in provider.get_components():
                    if component.id in index:
                        raise ValueError(f"duplicate component id detected: `{component.id}`")
                    index[component.id] = provider
            self._component_provider_index = index
        try:
            return self._component_provider_index[component_id]
        except KeyError as exc:
            raise ValueError(f"unknown component id: `{component_id}`") from exc


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
