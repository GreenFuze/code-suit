from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.core.quality.quality_intelligence import QualityIntelligence
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.quality_models import QualityEntityDelta, QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase


class _FakeRepository:
    def __init__(self, providers, roles):
        self._providers = providers
        self.provider_roles = roles
        self.root = Path("/repo")

    def get_providers_for_role(self, role: ProviderRole):
        return tuple(
            provider
            for provider_id, provider in self._providers.items()
            if role in self.provider_roles[provider_id]
        )

    def get_provider(self, provider_id: str):
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"unknown provider id for repository `{self.root}`: `{provider_id}`")
        return provider


class _QualityProvider(QualityProviderBase):
    PROVIDER_ID = "fake-quality"
    DISPLAY_NAME = "fake-quality"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.QUALITY})

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return QualityFileResult(
            repository_rel_path=repository_rel_path,
            tool="fake",
            operation="lint",
            changed=is_fix,
            success=True,
            message=None,
            diagnostics=tuple(),
            entity_delta=QualityEntityDelta(),
            applied_fixes=is_fix,
            content_sha_before="before",
            content_sha_after="after" if is_fix else "before",
        )

    def format_file(self, repository_rel_path: str) -> QualityFileResult:
        return QualityFileResult(
            repository_rel_path=repository_rel_path,
            tool="fake",
            operation="format",
            changed=True,
            success=True,
            message=None,
            diagnostics=tuple(),
            entity_delta=QualityEntityDelta(),
            applied_fixes=True,
            content_sha_before="before",
            content_sha_after="after",
        )


def test_quality_intelligence_dispatches_to_selected_provider() -> None:
    provider = _QualityProvider(repository=None)  # type: ignore[arg-type]
    repo = _FakeRepository({"fake-quality": provider}, {"fake-quality": frozenset({ProviderRole.QUALITY})})
    intelligence = QualityIntelligence(repo)  # type: ignore[arg-type]

    assert intelligence.provider_ids == ("fake-quality",)
    assert intelligence.lint_file("file.ts", is_fix=True, provider_id="fake-quality").applied_fixes is True
    assert intelligence.format_file("file.ts", provider_id="fake-quality").tool == "fake"


def test_quality_intelligence_rejects_unknown_provider() -> None:
    provider = _QualityProvider(repository=None)  # type: ignore[arg-type]
    repo = _FakeRepository({"fake-quality": provider}, {"fake-quality": frozenset({ProviderRole.QUALITY})})
    intelligence = QualityIntelligence(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unknown provider id"):
        intelligence.lint_file("file.ts", is_fix=False, provider_id="missing")


def test_quality_intelligence_rejects_provider_without_quality_role() -> None:
    provider = _QualityProvider(repository=None)  # type: ignore[arg-type]
    repo = _FakeRepository({"fake-quality": provider}, {"fake-quality": frozenset()})
    intelligence = QualityIntelligence(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="does not support quality"):
        intelligence.format_file("file.ts", provider_id="fake-quality")
