from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.providers.provider_metadata import ProviderDescriptor
from suitcode.providers.provider_roles import ProviderRole

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ProviderBase(ABC):
    PROVIDER_ID = ""
    DISPLAY_NAME = ""
    BUILD_SYSTEMS: tuple[str, ...] = tuple()
    PROGRAMMING_LANGUAGES: tuple[str, ...] = tuple()

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    @property
    def repository(self) -> Repository:
        return self._repository

    @classmethod
    def descriptor(cls) -> ProviderDescriptor:
        provider_id = cls.PROVIDER_ID.strip()
        display_name = cls.DISPLAY_NAME.strip()
        if not provider_id:
            raise ValueError(f"{cls.__name__} must define a non-empty PROVIDER_ID")
        if not display_name:
            raise ValueError(f"{cls.__name__} must define a non-empty DISPLAY_NAME")
        if not isinstance(cls.BUILD_SYSTEMS, tuple):
            raise ValueError(f"{cls.__name__}.BUILD_SYSTEMS must be a tuple[str, ...]")
        if not isinstance(cls.PROGRAMMING_LANGUAGES, tuple):
            raise ValueError(f"{cls.__name__}.PROGRAMMING_LANGUAGES must be a tuple[str, ...]")

        return ProviderDescriptor(
            provider_id=provider_id,
            display_name=display_name,
            build_systems=cls.BUILD_SYSTEMS,
            programming_languages=cls.PROGRAMMING_LANGUAGES,
            supported_roles=cls.supported_roles(),
        )

    @classmethod
    def supported_roles(cls) -> frozenset[ProviderRole]:
        from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
        from suitcode.providers.code_provider_base import CodeProviderBase
        from suitcode.providers.quality_provider_base import QualityProviderBase
        from suitcode.providers.test_provider_base import TestProviderBase

        roles: set[ProviderRole] = set()
        if issubclass(cls, ArchitectureProviderBase):
            roles.add(ProviderRole.ARCHITECTURE)
        if issubclass(cls, CodeProviderBase):
            roles.add(ProviderRole.CODE)
        if issubclass(cls, TestProviderBase):
            roles.add(ProviderRole.TEST)
        if issubclass(cls, QualityProviderBase):
            roles.add(ProviderRole.QUALITY)
        return frozenset(roles)

    @classmethod
    @abstractmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        raise NotImplementedError
