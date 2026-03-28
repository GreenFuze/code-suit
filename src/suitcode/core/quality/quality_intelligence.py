from __future__ import annotations

from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.runtime_capability_models import QualityRuntimeCapabilities


class QualityIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[QualityProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_role(ProviderRole.QUALITY)
            if isinstance(provider, QualityProviderBase)
        )

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(provider.__class__.descriptor().provider_id for provider in self.providers)

    def provider_ids_for_files(self, repository_rel_paths: tuple[str, ...]) -> tuple[str, ...]:
        provider_ids: list[str] = []
        for provider in self._quality_providers_for_files(repository_rel_paths):
            provider_id = provider.__class__.descriptor().provider_id
            if provider_id not in provider_ids:
                provider_ids.append(provider_id)
        return tuple(provider_ids)

    def provider_ids_for_owner(self, owner_id: str) -> tuple[str, ...]:
        owned_files = self._repository.list_files_by_owner(owner_id)
        if not owned_files:
            return tuple()
        return self.provider_ids_for_files(tuple(file_info.repository_rel_path for file_info in owned_files))

    def lint_file(self, repository_rel_path: str, is_fix: bool, provider_id: str) -> QualityFileResult:
        provider = self._quality_provider_for_file(repository_rel_path, provider_id)
        return provider.lint_file(repository_rel_path, is_fix)

    def format_file(self, repository_rel_path: str, provider_id: str) -> QualityFileResult:
        provider = self._quality_provider_for_file(repository_rel_path, provider_id)
        return provider.format_file(repository_rel_path)

    def get_runtime_capabilities(
        self,
        repository_rel_paths: tuple[str, ...] | None = None,
    ) -> tuple[QualityRuntimeCapabilities, ...]:
        providers = self.providers if repository_rel_paths is None else self._quality_providers_for_files(repository_rel_paths)
        return tuple(provider.get_quality_runtime_capabilities(repository_rel_paths) for provider in providers)

    def _quality_providers_for_files(self, repository_rel_paths: tuple[str, ...]) -> tuple[QualityProviderBase, ...]:
        provider_ids: list[str] = []
        providers: list[QualityProviderBase] = []
        for repository_rel_path in repository_rel_paths:
            for provider in self._repository.get_providers_for_file_role(repository_rel_path, ProviderRole.QUALITY):
                key = (provider.__class__.descriptor().provider_id, provider.attachment.attachment_root_rel_path)
                if key in provider_ids:
                    continue
                provider_ids.append(key)
                if not isinstance(provider, QualityProviderBase):
                    raise ValueError(
                        f"provider `{provider.__class__.descriptor().provider_id}` does not implement quality operations"
                    )
                providers.append(provider)
        return tuple(providers)

    def _quality_provider_for_file(self, repository_rel_path: str, provider_id: str) -> QualityProviderBase:
        matches = tuple(
            provider
            for provider in self._quality_providers_for_files((repository_rel_path,))
            if provider.__class__.descriptor().provider_id == provider_id
        )
        if not matches:
            raise ValueError(
                f"provider `{provider_id}` does not support quality for `{repository_rel_path}` in repository `{self._repository.root}`"
            )
        return matches[0]


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
