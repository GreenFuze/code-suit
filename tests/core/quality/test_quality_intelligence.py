from __future__ import annotations

from pathlib import Path

import pytest

from suitcode.core.quality.quality_intelligence import QualityIntelligence
from suitcode.core.workspace import Workspace
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.provider_metadata import ProviderAttachmentCandidate, ProviderAttachmentContext
from suitcode.core.provenance_builders import lsp_delta_provenance, quality_tool_provenance
from suitcode.providers.quality_models import QualityEntityDelta, QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.runtime_capability_models import QualityRuntimeCapabilities, RuntimeCapability, RuntimeCapabilityAvailability
from suitcode.core.provenance import SourceKind


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

    def get_providers_for_file_role(self, repository_rel_path: str, role: ProviderRole):
        return self.get_providers_for_role(role)


class _QualityProvider(QualityProviderBase):
    PROVIDER_ID = "fake-quality"
    DISPLAY_NAME = "fake-quality"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def discover_attachments(cls, repository_root: Path) -> tuple[ProviderAttachmentCandidate, ...]:
        return (
            ProviderAttachmentCandidate(
                provider_id=cls.PROVIDER_ID,
                attachment_root=repository_root,
                detected_roles=frozenset({ProviderRole.QUALITY}),
            ),
        )

    def __init__(self, repository) -> None:
        super().__init__(
            repository,
            ProviderAttachmentContext(
                provider_id=self.PROVIDER_ID,
                repository_root=Path("/repo"),
                attachment_root=Path("/repo"),
                attachment_root_rel_path=".",
            ),
        )

    def lint_file(self, repository_rel_path: str, is_fix: bool) -> QualityFileResult:
        return QualityFileResult(
            repository_rel_path=repository_rel_path,
            tool="fake",
            operation="lint",
            changed=is_fix,
            success=True,
            message=None,
            diagnostics=tuple(),
            entity_delta=QualityEntityDelta(
                provenance=(
                    lsp_delta_provenance(
                        source_tool="fake-lsp",
                        evidence_summary=f"delta for `{repository_rel_path}`",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            ),
            applied_fixes=is_fix,
            content_sha_before="before",
            content_sha_after="after" if is_fix else "before",
            provenance=(
                quality_tool_provenance(
                    source_tool="fake",
                    evidence_summary=f"fake lint result for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
                lsp_delta_provenance(
                    source_tool="fake-lsp",
                    evidence_summary=f"quality result includes delta for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
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
            entity_delta=QualityEntityDelta(
                provenance=(
                    lsp_delta_provenance(
                        source_tool="fake-lsp",
                        evidence_summary=f"delta for `{repository_rel_path}`",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            ),
            applied_fixes=True,
            content_sha_before="before",
            content_sha_after="after",
            provenance=(
                quality_tool_provenance(
                    source_tool="fake",
                    evidence_summary=f"fake format result for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
                lsp_delta_provenance(
                    source_tool="fake-lsp",
                    evidence_summary=f"quality result includes delta for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                ),
            ),
        )

    def get_quality_runtime_capabilities(
        self,
        repository_rel_paths: tuple[str, ...] | None = None,
    ) -> QualityRuntimeCapabilities:
        lint = RuntimeCapability(
            capability_id="fake.quality.lint",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.QUALITY_TOOL,
            source_tool="fake",
            provenance=(
                quality_tool_provenance(
                    source_tool="fake",
                    evidence_summary="fake lint capability is available",
                    evidence_paths=("file.ts",),
                ),
            ),
        )
        format_capability = RuntimeCapability(
            capability_id="fake.quality.format",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.QUALITY_TOOL,
            source_tool="fake",
            provenance=(
                quality_tool_provenance(
                    source_tool="fake",
                    evidence_summary="fake format capability is available",
                    evidence_paths=("file.ts",),
                ),
            ),
        )
        return QualityRuntimeCapabilities(lint=lint, format=format_capability)


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

    with pytest.raises(ValueError, match="does not support quality"):
        intelligence.lint_file("file.ts", is_fix=False, provider_id="missing")


def test_quality_intelligence_rejects_provider_without_quality_role() -> None:
    provider = _QualityProvider(repository=None)  # type: ignore[arg-type]
    repo = _FakeRepository({"fake-quality": provider}, {"fake-quality": frozenset()})
    intelligence = QualityIntelligence(repo)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="does not support quality"):
        intelligence.format_file("file.ts", provider_id="fake-quality")


def test_quality_intelligence_excludes_runner_owned_files_from_repo_scope_only(tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "codegen": "node scripts/codegen.mjs"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    (repo_root / "scripts" / "codegen.mjs").write_text("console.log('codegen');\n", encoding="utf-8")

    repository = Workspace(repo_root).repositories[0]
    quality = repository.quality

    owner = repository.get_file_owner("scripts/codegen.mjs")

    assert owner.owner.kind == "runner"
    assert "scripts/codegen.mjs" not in quality.relevant_repository_rel_paths()
    assert quality.relevant_repository_rel_paths(("scripts/codegen.mjs",)) == ("scripts/codegen.mjs",)
    assert quality.provider_ids_for_files(("scripts/codegen.mjs",)) == ("npm",)
