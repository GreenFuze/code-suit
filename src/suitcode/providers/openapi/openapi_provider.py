from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.models import Aggregator, Component, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.models.graph_types import ComponentKind, ProgrammingLanguage
from suitcode.core.models.ids import make_file_id
from suitcode.core.provenance_builders import document_node_provenance, ownership_node_provenance
from suitcode.core.structured_artifact_models import StructuredArtifact, StructuredArtifactKind
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.openapi.parser import parse_openapi_document
from suitcode.providers.provider_metadata import ProviderAttachmentCandidate, ProviderAttachmentContext
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.structured_artifact_provider_base import StructuredArtifactProviderBase

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class OpenApiProvider(ArchitectureProviderBase, StructuredArtifactProviderBase):
    PROVIDER_ID = "openapi"
    DISPLAY_NAME = "openapi"
    BUILD_SYSTEMS = tuple()
    PROGRAMMING_LANGUAGES = ("yaml", "json")
    _OWNER_ID = "component:openapi:specs"
    _IGNORED_DIR_NAMES = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
            ".bzr",
            ".suit",
            "node_modules",
            "vendor",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "venv",
            "dist",
            "build",
            "target",
            "out",
            ".next",
            ".nuxt",
            ".cache",
        }
    )
    _FILENAMES = frozenset(
        {
            "openapi.yaml",
            "openapi.yml",
            "openapi.json",
            "swagger.yaml",
            "swagger.yml",
            "swagger.json",
        }
    )

    @classmethod
    def discover_attachments(cls, repository_root: Path) -> tuple[ProviderAttachmentCandidate, ...]:
        root = repository_root.expanduser().resolve()
        if not tuple(cls._iter_spec_files(root)):
            return tuple()
        return (
            ProviderAttachmentCandidate(
                provider_id=cls.PROVIDER_ID,
                attachment_root=root,
                detected_roles=frozenset({ProviderRole.ARCHITECTURE}),
                discovery_notes=("OpenAPI structure support is available for well-known OpenAPI/Swagger files under the repository root",),
            ),
        )

    def __init__(self, repository: "Repository", attachment: ProviderAttachmentContext) -> None:
        super().__init__(repository, attachment)
        self._spec_files = tuple(sorted(self._repository_rel_paths()))

    def get_components(self) -> tuple[Component, ...]:
        if not self._spec_files:
            return tuple()
        return (
            Component(
                id=self._OWNER_ID,
                name="OpenAPI Specifications",
                component_kind=ComponentKind.OTHER,
                language=ProgrammingLanguage.OTHER,
                source_roots=(self.attachment_root_rel_path,),
                artifact_paths=tuple(),
                provenance=(
                    document_node_provenance(
                        evidence_summary=f"OpenAPI specification component derived from {len(self._spec_files)} specification files",
                        evidence_paths=self._spec_files[:10],
                        source_tool="openapi",
                    ),
                ),
            ),
        )

    def get_aggregators(self) -> tuple[Aggregator, ...]:
        return tuple()

    def get_runners(self) -> tuple[Runner, ...]:
        return tuple()

    def get_package_managers(self) -> tuple[PackageManager, ...]:
        return tuple()

    def get_external_packages(self) -> tuple[ExternalPackage, ...]:
        return tuple()

    def get_files(self) -> tuple[FileInfo, ...]:
        return tuple(
            FileInfo(
                id=make_file_id(repository_rel_path),
                name=Path(repository_rel_path).name,
                repository_rel_path=repository_rel_path,
                language=ProgrammingLanguage.OTHER,
                owner_id=self._OWNER_ID,
                provenance=(
                    ownership_node_provenance(
                        evidence_summary=f"OpenAPI file ownership assigned by openapi provider for `{repository_rel_path}`",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            )
            for repository_rel_path in self._spec_files
        )

    def get_component_dependency_edges(self, component_id: str | None = None) -> tuple[ComponentDependencyEdge, ...]:
        return tuple()

    def describe_structured_artifact(self, repository_rel_path: str) -> StructuredArtifact | None:
        normalized_path = repository_rel_path.strip().replace("\\", "/")
        if normalized_path not in self._spec_files:
            return None
        openapi = parse_openapi_document(self.repository.root / normalized_path, normalized_path)
        return StructuredArtifact(
            artifact_kind=StructuredArtifactKind.OPENAPI_DOCUMENT,
            openapi=openapi,
            provenance=openapi.provenance,
        )

    @classmethod
    def _iter_spec_files(cls, repository_root: Path):
        for current_root, dirnames, filenames in os.walk(repository_root):
            dirnames[:] = sorted(name for name in dirnames if name not in cls._IGNORED_DIR_NAMES)
            current_path = Path(current_root)
            for filename in sorted(filenames):
                if filename.lower() not in cls._FILENAMES:
                    continue
                yield current_path / filename

    def _repository_rel_paths(self) -> tuple[str, ...]:
        return tuple(
            path.relative_to(self.repository.root).as_posix()
            for path in self._iter_spec_files(self.repository.root)
        )
