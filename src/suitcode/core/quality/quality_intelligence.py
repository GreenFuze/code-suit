from __future__ import annotations

from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase


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

    def lint_file(self, repository_rel_path: str, is_fix: bool, provider_id: str) -> QualityFileResult:
        provider = self._get_quality_provider(provider_id)
        return provider.lint_file(repository_rel_path, is_fix)

    def format_file(self, repository_rel_path: str, provider_id: str) -> QualityFileResult:
        provider = self._get_quality_provider(provider_id)
        return provider.format_file(repository_rel_path)

    def _get_quality_provider(self, provider_id: str) -> QualityProviderBase:
        provider = self._repository.get_provider(provider_id)
        if ProviderRole.QUALITY not in self._repository.provider_roles.get(provider_id, frozenset()):
            raise ValueError(f"provider `{provider_id}` does not support quality for repository `{self._repository.root}`")
        if not isinstance(provider, QualityProviderBase):
            raise ValueError(f"provider `{provider_id}` does not implement quality operations")
        return provider


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
