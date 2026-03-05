from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentContext, FileContext, SymbolContext
from suitcode.core.component_context_resolver import ComponentContextResolver
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.code_reference_service import CodeReferenceService
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, lsp_provenance, ownership_provenance
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
            related_tests = self._repository.tests.get_related_tests(RelatedTestTarget(repository_rel_path=repository_rel_path))
            contexts.append(
                FileContext(
                    file_info=file_owner.file_info,
                    owner=file_owner.owner,
                    symbol_count=len(symbols),
                    symbols_preview=symbols[:symbol_preview_limit],
                    related_test_count=len(related_tests),
                    related_tests_preview=related_tests[:test_preview_limit],
                    quality_provider_ids=self._repository.quality.provider_ids,
                    provenance=self._file_context_provenance(repository_rel_path, symbols, related_tests),
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

    def _file_context_provenance(self, repository_rel_path: str, symbols, related_tests) -> tuple[ProvenanceEntry, ...]:
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
        return "typescript-language-server"
