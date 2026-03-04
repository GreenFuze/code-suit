from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from suitcode.providers.provider_roles import ProviderRole


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    display_name: str
    build_systems: tuple[str, ...]
    programming_languages: tuple[str, ...]
    supported_roles: frozenset[ProviderRole]


@dataclass(frozen=True)
class DetectedProviderSupport:
    descriptor: ProviderDescriptor
    detected_roles: frozenset[ProviderRole]

    @property
    def provider_id(self) -> str:
        return self.descriptor.provider_id


@dataclass(frozen=True)
class RepositorySupportResult:
    repository_root: Path
    detected_providers: tuple[DetectedProviderSupport, ...]

    @property
    def is_supported(self) -> bool:
        return bool(self.detected_providers)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(item.provider_id for item in self.detected_providers)
