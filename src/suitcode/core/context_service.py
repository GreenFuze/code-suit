from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentContext, FileContext, FileRelationshipKind, RenderEdgeKind, SymbolContext
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, lsp_provenance, ownership_provenance
from suitcode.core.provenance_summary import preferred_source_tool
from suitcode.core.tests.provenance import is_authoritative_test_provenance
from suitcode.core.tests.models import RelatedTestTarget

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ContextService:
    def __init__(
        self,
        repository: Repository,
        ownership_index: OwnershipIndex,
        component_context_resolver: ComponentContextResolver,
        code_reference_service: CodeReferenceService,
    ) -> None:
        self._repository = repository
        self._ownership_index = ownership_index
        self._component_context_resolver = component_context_resolver
        self._code_reference_service = code_reference_service

    def describe_components(
        self,
        component_ids: tuple[str, ...],
        file_preview_limit: int,
        dependency_preview_limit: int,
        dependent_preview_limit: int,
        test_preview_limit: int,
    ) -> tuple[ComponentContext, ...]:
        self._validate_exact_batch(component_ids, "component_ids")
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        contexts: list[ComponentContext] = []
        for component_id in component_ids:
            try:
                component = components_by_id[component_id]
            except KeyError as exc:
                raise ValueError(f"unknown component id: `{component_id}`") from exc
            owned_files = self._ownership_index.files_for_owner(component_id)
            related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(owner_id=component_id))
            dependencies = self._repository.arch.get_component_dependencies(component_id)
            dependents = self._repository.arch.get_component_dependents(component_id)
            contexts.append(
                ComponentContext(
                    component=component,
                    owned_file_count=len(owned_files),
                    owned_files_preview=owned_files[:file_preview_limit],
                    runner_ids=self._component_context_resolver.related_runner_ids_for_component(component, owned_files),
                    related_test_ids=tuple(item.match.test_definition.id for item in related_tests[:test_preview_limit]),
                    dependency_count=len(dependencies),
                    dependencies_preview=dependencies[:dependency_preview_limit],
                    dependent_count=len(dependents),
                    dependents_preview=dependents[:dependent_preview_limit],
                    provenance=self._component_context_provenance(
                        component_id,
                        owned_files,
                        dependencies,
                        related_tests,
                    ),
                )
            )
        return tuple(contexts)

    def describe_files(
        self,
        repository_rel_paths: tuple[str, ...],
        symbol_preview_limit: int,
        test_preview_limit: int,
    ) -> tuple[FileContext, ...]:
        self._validate_exact_batch(repository_rel_paths, "repository_rel_paths")
        contexts: list[FileContext] = []
        for repository_rel_path in repository_rel_paths:
            file_owner = self._ownership_index.owner_for_file(repository_rel_path)
            symbols = self._repository.code.list_symbols_in_file(repository_rel_path)
            reference_sites = self._code_reference_service.references_for_file(repository_rel_path)
            dependency_files = self._repository.code.get_file_relationships(
                repository_rel_path,
                relationship_kind=FileRelationshipKind.IMPORTS,
            )
            dependent_files = self._repository.code.get_file_relationships(
                repository_rel_path,
                relationship_kind=FileRelationshipKind.IMPORTED_BY,
            )
            render_children = self._repository.code.get_file_render_edges(
                repository_rel_path,
                relationship_kind=RenderEdgeKind.RENDERS,
            )
            render_parents = self._repository.code.get_file_render_edges(
                repository_rel_path,
                relationship_kind=RenderEdgeKind.RENDERED_BY,
            )
            invariant_findings = self._repository.code.get_file_invariant_findings(repository_rel_path)
            local_flow_edges = self._repository.code.get_file_local_flow_edges(repository_rel_path)
            implementation_locations = self._repository.code.get_file_implementation_locations(repository_rel_path)
            related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=repository_rel_path))
            contexts.append(
                FileContext(
                    file_info=file_owner.file_info,
                    owner=file_owner.owner,
                    symbol_count=len(symbols),
                    symbols_preview=symbols[:symbol_preview_limit],
                    reference_site_count=len(reference_sites),
                    reference_sites_preview=reference_sites[:symbol_preview_limit],
                    dependency_file_count=len(dependency_files),
                    dependency_files_preview=dependency_files[:symbol_preview_limit],
                    dependent_file_count=len(dependent_files),
                    dependent_files_preview=dependent_files[:symbol_preview_limit],
                    render_child_count=len(render_children),
                    render_children_preview=render_children[:symbol_preview_limit],
                    render_parent_count=len(render_parents),
                    render_parents_preview=render_parents[:symbol_preview_limit],
                    invariant_finding_count=len(invariant_findings),
                    invariant_findings_preview=invariant_findings[:symbol_preview_limit],
                    local_flow_edge_count=len(local_flow_edges),
                    local_flow_edges_preview=local_flow_edges[:symbol_preview_limit],
                    implementation_location_count=len(implementation_locations),
                    implementation_locations_preview=implementation_locations[:symbol_preview_limit],
                    related_test_count=len(related_tests),
                    related_tests_preview=related_tests[:test_preview_limit],
                    quality_provider_ids=self._repository.quality.provider_ids_for_files(
                        (file_owner.file_info.repository_rel_path,)
                    ),
                    provenance=self._file_context_provenance(
                        repository_rel_path,
                        symbols,
                        reference_sites,
                        dependency_files,
                        dependent_files,
                        render_children,
                        render_parents,
                        invariant_findings,
                        local_flow_edges,
                        implementation_locations,
                        related_tests,
                    ),
                )
            )
        return tuple(contexts)

    def describe_symbol_context(
        self,
        symbol_id: str,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> SymbolContext:
        symbol = self._code_reference_service.resolve_symbol(symbol_id)
        file_owner = self._ownership_index.owner_for_file(symbol.repository_rel_path)
        definitions = self._repository.code.find_definition_by_symbol_id(symbol_id)
        references = self._repository.code.find_references_by_symbol_id(symbol_id)
        related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=symbol.repository_rel_path))
        return SymbolContext(
            symbol=symbol,
            owner=file_owner.owner,
            definition_count=len(definitions),
            definitions=definitions,
            reference_count=len(references),
            references_preview=references[:reference_preview_limit],
            related_test_count=len(related_tests),
            related_tests_preview=related_tests[:test_preview_limit],
            provenance=self._symbol_context_provenance(symbol.repository_rel_path, related_tests),
        )

    @staticmethod
    def _validate_exact_batch(items: tuple[str, ...], field_name: str) -> None:
        if not items:
            raise ValueError(f"{field_name} must not be empty")
        if any(not item.strip() for item in items):
            raise ValueError(f"{field_name} must not contain empty values")
        if len(set(items)) != len(items):
            raise ValueError(f"{field_name} must not contain duplicates")

    def _component_context_provenance(
        self,
        component_id: str,
        owned_files,
        dependencies,
        related_tests,
    ) -> tuple[ProvenanceEntry, ...]:
        entries: list[ProvenanceEntry] = [
            ownership_provenance(
                evidence_summary=f"component context derived from ownership index for `{component_id}`",
                evidence_paths=tuple(item.repository_rel_path for item in owned_files[:10]),
            )
        ]
        if dependencies:
            dependency_paths = self._summarized_dependency_paths(dependencies)
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.MANIFEST,
                    evidence_summary=f"dependency context summarized from {len(dependencies)} declared component dependencies",
                    evidence_paths=dependency_paths,
                )
            )
        if related_tests:
            entries.append(self._summarized_test_provenance(related_tests, "component-related tests"))
        return tuple(entries)

    def _file_context_provenance(
        self,
        repository_rel_path: str,
        symbols,
        reference_sites,
        dependency_files,
        dependent_files,
        render_children,
        render_parents,
        invariant_findings,
        local_flow_edges,
        implementation_locations,
        related_tests,
    ) -> tuple[ProvenanceEntry, ...]:
        entries: list[ProvenanceEntry] = [
            ownership_provenance(
                evidence_summary=f"file context derived from ownership index for `{repository_rel_path}`",
                evidence_paths=(repository_rel_path,),
            )
        ]
        if symbols:
            entries.append(
                lsp_provenance(
                    source_tool=self._lsp_tool_for_path(repository_rel_path),
                    evidence_summary=f"file symbols derived from LSP document symbols for `{repository_rel_path}`",
                    evidence_paths=(repository_rel_path,),
                )
            )
        if reference_sites:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.LSP,
                    source_tool=self._reference_source_tool(repository_rel_path, reference_sites),
                    evidence_summary=f"exact reference sites derived from deterministic symbol-reference queries for `{repository_rel_path}`",
                    evidence_paths=self._summarized_reference_paths(repository_rel_path, reference_sites),
                )
            )
        if dependency_files or dependent_files:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._relationship_source_tool(repository_rel_path, dependency_files, dependent_files),
                    evidence_summary=(
                        f"file relationships derived from deterministic dependency-graph resolution for `{repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_relationship_paths(
                        repository_rel_path,
                        dependency_files,
                        dependent_files,
                    ),
                )
            )
        if render_children or render_parents:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._render_source_tool(repository_rel_path, render_children, render_parents),
                    evidence_summary=(
                        f"UI render relationships derived from deterministic JSX component resolution for `{repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_render_paths(
                        repository_rel_path,
                        render_children,
                        render_parents,
                    ),
                )
            )
        if invariant_findings or local_flow_edges:
            entries.append(
                derived_summary_provenance(
                    source_kind=SourceKind.DEPENDENCY_GRAPH,
                    source_tool=self._static_analysis_source_tool(repository_rel_path, invariant_findings, local_flow_edges),
                    evidence_summary=(
                        f"file context includes deterministic TypeScript static analysis findings for `{repository_rel_path}`"
                    ),
                    evidence_paths=self._summarized_static_analysis_paths(
                        repository_rel_path,
                        invariant_findings,
                        local_flow_edges,
                    ),
                )
            )
        if implementation_locations:
            entries.append(
                lsp_provenance(
                    source_tool=self._lsp_tool_for_path(repository_rel_path),
                    evidence_summary=f"implementation candidates derived from deterministic LSP implementation queries for `{repository_rel_path}`",
                    evidence_paths=self._summarized_implementation_paths(repository_rel_path, implementation_locations),
                )
            )
        if related_tests:
            entries.append(self._summarized_test_provenance(related_tests, "file-related tests"))
        return tuple(entries)

    def _symbol_context_provenance(self, repository_rel_path: str, related_tests) -> tuple[ProvenanceEntry, ...]:
        entries: list[ProvenanceEntry] = [
            lsp_provenance(
                source_tool=self._lsp_tool_for_path(repository_rel_path),
                evidence_summary=f"symbol context derived from LSP symbol, definition, and reference queries for `{repository_rel_path}`",
                evidence_paths=(repository_rel_path,),
            )
        ]
        if related_tests:
            entries.append(self._summarized_test_provenance(related_tests, "symbol-related tests"))
        return tuple(entries)

    @staticmethod
    def _summarized_dependency_paths(dependencies) -> tuple[str, ...]:
        paths: list[str] = []
        for dependency in dependencies:
            for provenance in dependency.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_relationship_paths(repository_rel_path: str, dependency_files, dependent_files) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for item in (*dependency_files, *dependent_files):
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_reference_paths(repository_rel_path: str, reference_sites) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for item in reference_sites:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_render_paths(repository_rel_path: str, render_children, render_parents) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for item in (*render_children, *render_parents):
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_implementation_paths(repository_rel_path: str, implementation_locations) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for item in implementation_locations:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for provenance in item.provenance:
                for path in provenance.evidence_paths:
                    if path not in paths:
                        paths.append(path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_static_analysis_paths(repository_rel_path: str, invariant_findings, local_flow_edges) -> tuple[str, ...]:
        paths: list[str] = [repository_rel_path]
        for item in invariant_findings:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
            for producer in item.producer_sites_preview:
                if producer.repository_rel_path not in paths:
                    paths.append(producer.repository_rel_path)
        for item in local_flow_edges:
            if item.repository_rel_path not in paths:
                paths.append(item.repository_rel_path)
        return tuple(paths[:10])

    @staticmethod
    def _summarized_test_provenance(related_tests, label: str) -> ProvenanceEntry:
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

    @staticmethod
    def _relationship_source_tool(repository_rel_path: str, dependency_files, dependent_files) -> str | None:
        provenance = tuple(
            entry
            for item in (*dependency_files, *dependent_files)
            for entry in item.provenance
        )
        return preferred_source_tool(provenance) if provenance else ContextService._lsp_tool_for_path(repository_rel_path)

    @staticmethod
    def _reference_source_tool(repository_rel_path: str, reference_sites) -> str | None:
        provenance = tuple(
            entry
            for item in reference_sites
            for entry in item.provenance
        )
        return preferred_source_tool(provenance) if provenance else ContextService._lsp_tool_for_path(repository_rel_path)

    @staticmethod
    def _render_source_tool(repository_rel_path: str, render_children, render_parents) -> str | None:
        provenance = tuple(
            entry
            for item in (*render_children, *render_parents)
            for entry in item.provenance
        )
        return preferred_source_tool(provenance) if provenance else ContextService._lsp_tool_for_path(repository_rel_path)

    @staticmethod
    def _static_analysis_source_tool(repository_rel_path: str, invariant_findings, local_flow_edges) -> str | None:
        provenance = tuple(
            entry
            for item in (*invariant_findings, *local_flow_edges)
            for entry in item.provenance
        )
        return preferred_source_tool(provenance) if provenance else ContextService._lsp_tool_for_path(repository_rel_path)
