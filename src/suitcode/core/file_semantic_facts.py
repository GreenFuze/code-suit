from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from suitcode.core.code.evidence_tier import CodeEvidenceTier
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.intelligence_models import (
    FileContext,
    FileRelationshipKind,
    InvariantFindingRef,
    RenderEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, lsp_provenance, ownership_provenance
from suitcode.core.provenance_summary import preferred_source_tool
from suitcode.core.tests.models import RelatedTestTarget, ResolvedRelatedTest
from suitcode.core.tests.provenance import is_authoritative_test_provenance

if TYPE_CHECKING:
    from suitcode.core.code.models import CodeLocation
    from suitcode.core.code_reference_service import CodeReferenceService
    from suitcode.core.intelligence_models import FileRelationshipRef, RenderEdgeRef
    from suitcode.core.models import EntityInfo
    from suitcode.core.repository import Repository
    from suitcode.core.repository_models import FileOwnerInfo


@dataclass(frozen=True, slots=True)
class FileSemanticFactsKey:
    repository_rel_path: str
    evidence_tier: CodeEvidenceTier


class FileSemanticFactsBundle:
    def __init__(
        self,
        repository: Repository,
        ownership_index: OwnershipIndex,
        code_reference_service: CodeReferenceService,
        repository_rel_path: str,
        evidence_tier: CodeEvidenceTier,
    ) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._code_reference_service = code_reference_service
        self._repository_rel_path = normalize_repository_relative_path(repository_rel_path)
        self._evidence_tier = evidence_tier
        self._file_owner: FileOwnerInfo | None = None
        self._symbols: tuple[EntityInfo, ...] | None = None
        self._reference_sites: tuple[CodeLocation, ...] | None = None
        self._dependency_files: tuple[FileRelationshipRef, ...] | None = None
        self._dependent_files: tuple[FileRelationshipRef, ...] | None = None
        self._render_children: tuple[RenderEdgeRef, ...] | None = None
        self._render_parents: tuple[RenderEdgeRef, ...] | None = None
        self._invariant_findings: tuple[InvariantFindingRef, ...] | None = None
        self._local_flow_edges: tuple[StaticFlowEdgeRef, ...] | None = None
        self._implementation_locations: tuple[CodeLocation, ...] | None = None
        self._related_tests: tuple[ResolvedRelatedTest, ...] | None = None
        self._quality_provider_ids: tuple[str, ...] | None = None

    @property
    def repository_rel_path(self) -> str:
        return self._repository_rel_path

    @property
    def evidence_tier(self) -> CodeEvidenceTier:
        return self._evidence_tier

    @property
    def file_owner(self) -> FileOwnerInfo:
        if self._file_owner is None:
            self._file_owner = self._ownership_index.owner_for_file(self._repository_rel_path)
        return self._file_owner

    @property
    def symbols(self) -> tuple[EntityInfo, ...]:
        if self._symbols is None:
            self._symbols = (
                self._repository.code.list_structural_symbols_in_file(self._repository_rel_path)
                if self._evidence_tier == CodeEvidenceTier.STRUCTURAL
                else self._repository.code.list_symbols_in_file(self._repository_rel_path)
            )
        return self._symbols

    @property
    def reference_sites(self) -> tuple[CodeLocation, ...]:
        if self._reference_sites is None:
            self._reference_sites = (
                tuple()
                if self._evidence_tier == CodeEvidenceTier.STRUCTURAL
                else self._code_reference_service.references_for_file(self._repository_rel_path)
            )
        return self._reference_sites

    @property
    def dependency_files(self) -> tuple[FileRelationshipRef, ...]:
        if self._dependency_files is None:
            self._dependency_files = self._repository.code.get_file_relationships(
                self._repository_rel_path,
                relationship_kind=FileRelationshipKind.IMPORTS,
                evidence_tier=self._evidence_tier,
            )
        return self._dependency_files

    @property
    def dependent_files(self) -> tuple[FileRelationshipRef, ...]:
        if self._dependent_files is None:
            self._dependent_files = self._repository.code.get_file_relationships(
                self._repository_rel_path,
                relationship_kind=FileRelationshipKind.IMPORTED_BY,
                evidence_tier=self._evidence_tier,
            )
        return self._dependent_files

    @property
    def render_children(self) -> tuple[RenderEdgeRef, ...]:
        if self._render_children is None:
            self._render_children = self._repository.code.get_file_render_edges(
                self._repository_rel_path,
                relationship_kind=RenderEdgeKind.RENDERS,
            )
        return self._render_children

    @property
    def render_parents(self) -> tuple[RenderEdgeRef, ...]:
        if self._render_parents is None:
            self._render_parents = self._repository.code.get_file_render_edges(
                self._repository_rel_path,
                relationship_kind=RenderEdgeKind.RENDERED_BY,
            )
        return self._render_parents

    @property
    def invariant_findings(self) -> tuple[InvariantFindingRef, ...]:
        if self._invariant_findings is None:
            self._invariant_findings = (
                tuple()
                if self._evidence_tier == CodeEvidenceTier.STRUCTURAL
                else self._repository.code.get_file_invariant_findings(self._repository_rel_path)
            )
        return self._invariant_findings

    @property
    def local_flow_edges(self) -> tuple[StaticFlowEdgeRef, ...]:
        if self._local_flow_edges is None:
            self._local_flow_edges = (
                tuple()
                if self._evidence_tier == CodeEvidenceTier.STRUCTURAL
                else self._repository.code.get_file_local_flow_edges(self._repository_rel_path)
            )
        return self._local_flow_edges

    @property
    def implementation_locations(self) -> tuple[CodeLocation, ...]:
        if self._implementation_locations is None:
            self._implementation_locations = (
                tuple()
                if self._evidence_tier == CodeEvidenceTier.STRUCTURAL
                else self._repository.code.get_file_implementation_locations(self._repository_rel_path)
            )
        return self._implementation_locations

    @property
    def related_tests(self) -> tuple[ResolvedRelatedTest, ...]:
        if self._related_tests is None:
            self._related_tests = self._repository.tests.get_related_tests(
                RelatedTestTarget(repository_rel_path=self._repository_rel_path)
            )
        return self._related_tests

    @property
    def quality_provider_ids(self) -> tuple[str, ...]:
        if self._quality_provider_ids is None:
            self._quality_provider_ids = self._repository.quality.provider_ids_for_files((self._repository_rel_path,))
        return self._quality_provider_ids

    def build_file_context(
        self,
        *,
        symbol_preview_limit: int,
        test_preview_limit: int,
        include_reference_sites: bool = True,
        include_implementation_locations: bool = True,
        reference_site_limit: int | None = None,
    ) -> FileContext:
        reference_sites = (
            self.reference_sites[:reference_site_limit]
            if include_reference_sites and reference_site_limit is not None
            else (self.reference_sites if include_reference_sites else tuple())
        )
        implementation_locations = self.implementation_locations if include_implementation_locations else tuple()
        return FileContext(
            file_info=self.file_owner.file_info,
            owner=self.file_owner.owner,
            symbol_count=len(self.symbols),
            symbols_preview=self.symbols[:symbol_preview_limit],
            reference_site_count=len(reference_sites),
            reference_sites_preview=reference_sites[:symbol_preview_limit],
            dependency_file_count=len(self.dependency_files),
            dependency_files_preview=self.dependency_files[:symbol_preview_limit],
            dependent_file_count=len(self.dependent_files),
            dependent_files_preview=self.dependent_files[:symbol_preview_limit],
            render_child_count=len(self.render_children),
            render_children_preview=self.render_children[:symbol_preview_limit],
            render_parent_count=len(self.render_parents),
            render_parents_preview=self.render_parents[:symbol_preview_limit],
            invariant_finding_count=len(self.invariant_findings),
            invariant_findings_preview=self.invariant_findings[:symbol_preview_limit],
            local_flow_edge_count=len(self.local_flow_edges),
            local_flow_edges_preview=self.local_flow_edges[:symbol_preview_limit],
            implementation_location_count=len(implementation_locations),
            implementation_locations_preview=implementation_locations[:symbol_preview_limit],
            related_test_count=len(self.related_tests),
            related_tests_preview=self.related_tests[:test_preview_limit],
            quality_provider_ids=self.quality_provider_ids,
            provenance=self._file_context_provenance(
                reference_sites=reference_sites,
                implementation_locations=implementation_locations,
            ),
        )

    def _file_context_provenance(
        self,
        *,
        reference_sites: tuple[CodeLocation, ...],
        implementation_locations: tuple[CodeLocation, ...],
    ) -> tuple[ProvenanceEntry, ...]:
        entries: list[ProvenanceEntry] = [
            ownership_provenance(
                evidence_summary=f"file context derived from ownership index for `{self._repository_rel_path}`",
                evidence_paths=(self._repository_rel_path,),
            )
        ]
        if self.symbols:
            entries.append(
                derived_summary_provenance(
                    source_kind=self._symbol_source_kind(self.symbols),
                    source_tool=self._symbol_source_tool(self.symbols),
                    evidence_summary=f"file symbols derived from deterministic code symbols for `{self._repository_rel_path}`",
                    evidence_paths=(self._repository_rel_path,),
                )
            )
        if reference_sites:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.LSP,
                    source_tool=self._reference_source_tool(reference_sites),
                    evidence_summary=(
                        f"exact reference sites derived from deterministic symbol-reference queries for "
                        f"`{self._repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_reference_paths(reference_sites),
                )
            )
        if self.dependency_files or self.dependent_files:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._relationship_source_tool(),
                    evidence_summary=(
                        f"file relationships derived from deterministic dependency-graph resolution for "
                        f"`{self._repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_relationship_paths(),
                )
            )
        if self.render_children or self.render_parents:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._render_source_tool(),
                    evidence_summary=(
                        f"UI render relationships derived from deterministic JSX component resolution for "
                        f"`{self._repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_render_paths(),
                )
            )
        if self.invariant_findings or self.local_flow_edges:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._static_analysis_source_tool(),
                    evidence_summary=(
                        f"file context includes deterministic TypeScript static analysis findings for "
                        f"`{self._repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_static_analysis_paths(),
                )
            )
        if implementation_locations:
            entries.append(
                lsp_provenance(
                    source_tool=self._lsp_tool_for_path(self._repository_rel_path),
                    evidence_summary=(
                        f"implementation candidates derived from deterministic LSP implementation queries for "
                        f"`{self._repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_implementation_paths(implementation_locations),
                )
            )
        if self.related_tests:
            entries.append(self._summarized_test_provenance(self.related_tests, "file-related tests"))
        return tuple(entries)

    def _relationship_source_tool(self) -> str | None:
        provenance = tuple(entry for item in (*self.dependency_files, *self.dependent_files) for entry in item.provenance)
        return preferred_source_tool(provenance) if provenance else self._lsp_tool_for_path(self._repository_rel_path)

    def _reference_source_tool(self, reference_sites: tuple[CodeLocation, ...]) -> str | None:
        provenance = tuple(entry for item in reference_sites for entry in item.provenance)
        return preferred_source_tool(provenance) if provenance else self._lsp_tool_for_path(self._repository_rel_path)

    def _render_source_tool(self) -> str | None:
        provenance = tuple(entry for item in (*self.render_children, *self.render_parents) for entry in item.provenance)
        return preferred_source_tool(provenance) if provenance else self._lsp_tool_for_path(self._repository_rel_path)

    def _static_analysis_source_tool(self) -> str | None:
        provenance = tuple(entry for item in (*self.invariant_findings, *self.local_flow_edges) for entry in item.provenance)
        return preferred_source_tool(provenance) if provenance else self._lsp_tool_for_path(self._repository_rel_path)

    @staticmethod
    def _symbol_source_kind(symbols: tuple[EntityInfo, ...]) -> SourceKind:
        provenance = tuple(entry for symbol in symbols for entry in symbol.provenance)
        if any(entry.source_kind == SourceKind.LSP for entry in provenance):
            return SourceKind.LSP
        if any(entry.source_kind == SourceKind.SYNTAX for entry in provenance):
            return SourceKind.SYNTAX
        return SourceKind.DEPENDENCY_GRAPH

    def _symbol_source_tool(self, symbols: tuple[EntityInfo, ...]) -> str | None:
        provenance = tuple(entry for symbol in symbols for entry in symbol.provenance)
        return preferred_source_tool(provenance) if provenance else self._lsp_tool_for_path(self._repository_rel_path)

    def _summarized_relationship_paths(self) -> tuple[str, ...]:
        paths: list[str] = [self._repository_rel_path]
        for item in (*self.dependency_files, *self.dependent_files):
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    def _summarized_reference_paths(self, reference_sites: tuple[CodeLocation, ...]) -> tuple[str, ...]:
        paths: list[str] = [self._repository_rel_path]
        for item in reference_sites:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    def _summarized_render_paths(self) -> tuple[str, ...]:
        paths: list[str] = [self._repository_rel_path]
        for item in (*self.render_children, *self.render_parents):
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    def _summarized_implementation_paths(self, implementation_locations: tuple[CodeLocation, ...]) -> tuple[str, ...]:
        paths: list[str] = [self._repository_rel_path]
        for item in implementation_locations:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    def _summarized_static_analysis_paths(self) -> tuple[str, ...]:
        paths: list[str] = [self._repository_rel_path]
        for item in self.invariant_findings:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for producer in item.producer_sites_preview:
                if producer.repository_rel_path not in paths:
                    paths.append(producer.repository_rel_path)
        for item in self.local_flow_edges:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_test_provenance(
        related_tests: tuple[ResolvedRelatedTest, ...],
        label: str,
    ) -> ProvenanceEntry:
        paths: list[str] = []
        authoritative = True
        for related_test in related_tests:
            authoritative = authoritative and is_authoritative_test_provenance(related_test.provenance)
            for provenance in related_test.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return ProvenanceEntry(
            confidence_mode=("authoritative" if authoritative else "derived"),
            source_kind=(SourceKind.TEST_TOOL if authoritative else SourceKind.HEURISTIC),
            source_tool=None,
            evidence_summary=f"{label} derived from discovered test metadata",
            evidence_paths=tuple(paths[:10]),
        )

    @staticmethod
    def _lsp_tool_for_path(repository_rel_path: str) -> str:
        lowered = repository_rel_path.lower()
        if lowered.endswith(".py"):
            return "basedpyright"
        if lowered.endswith(".go"):
            return "gopls"
        return "typescript-language-server"


class FileSemanticFactsService:
    def __init__(
        self,
        repository: Repository,
        ownership_index: OwnershipIndex,
        code_reference_service: CodeReferenceService,
    ) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._code_reference_service = code_reference_service
        self._bundles: dict[FileSemanticFactsKey, FileSemanticFactsBundle] = {}

    def get_bundle(
        self,
        repository_rel_path: str,
        *,
        evidence_tier: CodeEvidenceTier = CodeEvidenceTier.SEMANTIC,
    ) -> FileSemanticFactsBundle:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        key = FileSemanticFactsKey(repository_rel_path=normalized_path, evidence_tier=evidence_tier)
        bundle = self._bundles.get(key)
        if bundle is None:
            bundle = FileSemanticFactsBundle(
                self._repository,
                self._ownership_index,
                self._code_reference_service,
                normalized_path,
                evidence_tier,
            )
            self._bundles[key] = bundle
        return bundle

    def describe_file(
        self,
        repository_rel_path: str,
        *,
        symbol_preview_limit: int,
        test_preview_limit: int,
        include_reference_sites: bool = True,
        include_implementation_locations: bool = True,
        reference_site_limit: int | None = None,
        evidence_tier: CodeEvidenceTier = CodeEvidenceTier.SEMANTIC,
    ) -> FileContext:
        return self.get_bundle(repository_rel_path, evidence_tier=evidence_tier).build_file_context(
            symbol_preview_limit=symbol_preview_limit,
            test_preview_limit=test_preview_limit,
            include_reference_sites=include_reference_sites,
            include_implementation_locations=include_implementation_locations,
            reference_site_limit=reference_site_limit,
        )
