from __future__ import annotations

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget
from suitcode.core.intelligence_models import FileRelationshipKind, FileRelationshipRef, RenderEdgeKind, RenderEdgeRef
from suitcode.core.models import EntityInfo
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_source_tool
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import CodeRuntimeCapabilities


class CodeIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository

    @property
    def repository(self) -> "Repository":
        return self._repository

    @property
    def providers(self) -> tuple[CodeProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_role(ProviderRole.CODE)
            if isinstance(provider, CodeProviderBase)
        )

    def get_symbol(self, query: str, is_case_sensitive: bool = False) -> tuple[EntityInfo, ...]:
        if not query.strip():
            raise ValueError("query must not be blank")
        items: list[EntityInfo] = []
        for provider in self.providers:
            try:
                items.extend(provider.get_symbol(query, is_case_sensitive=is_case_sensitive))
            except ValueError:
                continue
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.repository_rel_path, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def list_symbols_in_file(
        self,
        repository_rel_path: str,
        query: str | None = None,
        is_case_sensitive: bool = False,
    ) -> tuple[EntityInfo, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        items: list[EntityInfo] = []
        for provider in self._providers_for_file(normalized_path):
            try:
                items.extend(
                    provider.list_symbols_in_file(
                        normalized_path,
                        query=query,
                        is_case_sensitive=is_case_sensitive,
                    )
                )
            except ValueError:
                continue
        return tuple(
            sorted(
                items,
                key=lambda item: (item.name, item.entity_kind, item.line_start or 0, item.column_start or 0, item.id),
            )
        )

    def find_definition(self, target: SymbolLookupTarget) -> tuple[CodeLocation, ...]:
        repository_rel_path, line, column = self._resolve_lookup_target(target)
        items: list[CodeLocation] = []
        for provider in self._providers_for_file(repository_rel_path):
            try:
                items.extend(provider.find_definition(repository_rel_path, line, column))
            except ValueError:
                continue
        return tuple(
            sorted(
                items,
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def get_runtime_capabilities(self) -> tuple[CodeRuntimeCapabilities, ...]:
        return tuple(provider.get_code_runtime_capabilities() for provider in self.providers)

    def get_file_implementation_locations(self, repository_rel_path: str) -> tuple[CodeLocation, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[str, int, int, int | None, int | None, str | None], CodeLocation] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_implementation_locations(normalized_path)
            except ValueError:
                continue
            for item in items:
                key = (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.line_end,
                    item.column_end,
                    item.symbol_id,
                )
                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue
                merged[key] = item.model_copy(
                    update={"provenance": tuple(dict.fromkeys((*existing.provenance, *item.provenance)))}
                )
        return tuple(
            sorted(
                merged.values(),
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def get_file_render_edges(
        self,
        repository_rel_path: str,
        relationship_kind: RenderEdgeKind | None = None,
    ) -> tuple[RenderEdgeRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[RenderEdgeKind, str, int, int, tuple[str, ...], bool], RenderEdgeRef] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_render_edges(normalized_path)
            except ValueError:
                continue
            for item in items:
                if relationship_kind is not None and item.relationship_kind != relationship_kind:
                    continue
                key = (
                    item.relationship_kind,
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.prop_names,
                    item.has_spread_props,
                )
                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue
                merged[key] = item.model_copy(
                    update={
                        "provenance": tuple(
                            dict.fromkeys((*existing.provenance, *item.provenance))
                        )
                    }
                )
        return tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    item.relationship_kind.value,
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.prop_names,
                    item.has_spread_props,
                ),
            )
        )

    def get_file_relationships(
        self,
        repository_rel_path: str,
        relationship_kind: FileRelationshipKind | None = None,
    ) -> tuple[FileRelationshipRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[FileRelationshipKind, str], FileRelationshipRef] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_relationships(normalized_path)
            except ValueError:
                continue
            for item in items:
                if relationship_kind is not None and item.relationship_kind != relationship_kind:
                    continue
                key = (item.relationship_kind, item.repository_rel_path)
                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue
                merged[key] = item.model_copy(
                    update={
                        "provenance": tuple(
                            dict.fromkeys((*existing.provenance, *item.provenance))
                        )
                    }
                )
        if not merged:
            for item in self._architecture_projected_file_relationships(normalized_path, relationship_kind):
                key = (item.relationship_kind, item.repository_rel_path)
                merged[key] = item
        return tuple(
            sorted(
                merged.values(),
                key=lambda item: (item.relationship_kind.value, item.repository_rel_path),
            )
        )

    def find_definition_by_symbol_id(self, symbol_id: str) -> tuple[CodeLocation, ...]:
        return self.find_definition(SymbolLookupTarget(symbol_id=symbol_id))

    def find_references(
        self,
        target: SymbolLookupTarget,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        repository_rel_path, line, column = self._resolve_lookup_target(target)
        items: list[CodeLocation] = []
        for provider in self._providers_for_file(repository_rel_path):
            try:
                items.extend(
                    provider.find_references(
                        repository_rel_path,
                        line,
                        column,
                        include_definition=include_definition,
                    )
                )
            except ValueError:
                continue
        return tuple(
            sorted(
                items,
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def find_references_by_symbol_id(
        self,
        symbol_id: str,
        include_definition: bool = False,
    ) -> tuple[CodeLocation, ...]:
        return self.find_references(SymbolLookupTarget(symbol_id=symbol_id), include_definition=include_definition)

    def find_implementations(self, target: SymbolLookupTarget) -> tuple[CodeLocation, ...]:
        repository_rel_path, line, column = self._resolve_lookup_target(target)
        items: list[CodeLocation] = []
        for provider in self._providers_for_file(repository_rel_path):
            try:
                items.extend(provider.find_implementations(repository_rel_path, line, column))
            except ValueError:
                continue
        return tuple(
            sorted(
                items,
                key=lambda item: (item.repository_rel_path, item.line_start, item.column_start, item.symbol_id or ""),
            )
        )

    def find_implementations_by_symbol_id(self, symbol_id: str) -> tuple[CodeLocation, ...]:
        return self.find_implementations(SymbolLookupTarget(symbol_id=symbol_id))

    def _resolve_lookup_target(self, target: SymbolLookupTarget) -> tuple[str, int, int]:
        if target.symbol_id is not None:
            return self._resolve_symbol_target(target.symbol_id)
        if target.repository_rel_path is None or target.line is None or target.column is None:
            raise ValueError(
                "lookup target must include `symbol_id` or (`repository_rel_path`, `line`, `column`)"
            )
        return normalize_repository_relative_path(target.repository_rel_path), target.line, target.column

    def _resolve_symbol_target(self, symbol_id: str) -> tuple[str, int, int]:
        if not symbol_id.startswith("entity:"):
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        parts = symbol_id.split(":")
        if len(parts) < 4:
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        repository_rel_path = normalize_repository_relative_path(parts[1])
        matches = [item for item in self.list_symbols_in_file(repository_rel_path) if item.id == symbol_id]
        if not matches:
            raise ValueError(f"symbol id could not be resolved: `{symbol_id}`")
        if len(matches) > 1:
            raise ValueError(f"symbol id resolved ambiguously: `{symbol_id}`")
        match = matches[0]
        if match.line_start is None or match.column_start is None:
            raise ValueError(f"symbol id has no usable location: `{symbol_id}`")
        return repository_rel_path, match.line_start, match.column_start

    def _providers_for_file(self, repository_rel_path: str) -> tuple[CodeProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_file_role(repository_rel_path, ProviderRole.CODE)
            if isinstance(provider, CodeProviderBase)
        )

    def _architecture_projected_file_relationships(
        self,
        repository_rel_path: str,
        relationship_kind: FileRelationshipKind | None,
    ) -> tuple[FileRelationshipRef, ...]:
        owner = self._repository.get_file_owner(repository_rel_path).owner
        primary_component = self._primary_component_for_file(repository_rel_path, owner.id)
        if primary_component is None:
            return tuple()
        components_by_id = {component.id: component for component in self._repository.arch.get_components()}
        relationships: dict[tuple[FileRelationshipKind, str], FileRelationshipRef] = {}

        if relationship_kind in (None, FileRelationshipKind.IMPORTS):
            for dependency in self._repository.arch.get_component_dependencies(primary_component.id):
                if dependency.target_kind != "component":
                    continue
                component = components_by_id.get(dependency.target_id)
                if component is None:
                    continue
                for artifact_path in component.artifact_paths:
                    if artifact_path == repository_rel_path:
                        continue
                    item = self._projected_relationship(
                        source_path=repository_rel_path,
                        target_path=artifact_path,
                        relationship_kind=FileRelationshipKind.IMPORTS,
                        target_component_name=component.name,
                        provenance=dependency.provenance,
                    )
                    relationships[(item.relationship_kind, item.repository_rel_path)] = item

        if relationship_kind in (None, FileRelationshipKind.IMPORTED_BY):
            for dependent_id in self._repository.arch.get_component_dependents(primary_component.id):
                component = components_by_id.get(dependent_id)
                if component is None:
                    continue
                dependency_edges = tuple(
                    edge
                    for edge in self._repository.arch.get_component_dependency_edges(dependent_id)
                    if edge.target_kind == "component" and edge.target_id == primary_component.id
                )
                if not dependency_edges:
                    continue
                merged_provenance = self._merge_provenance(*(edge.provenance for edge in dependency_edges))
                for artifact_path in component.artifact_paths:
                    if artifact_path == repository_rel_path:
                        continue
                    item = self._projected_relationship(
                        source_path=repository_rel_path,
                        target_path=artifact_path,
                        relationship_kind=FileRelationshipKind.IMPORTED_BY,
                        target_component_name=component.name,
                        provenance=merged_provenance,
                    )
                    relationships[(item.relationship_kind, item.repository_rel_path)] = item

        return tuple(
            sorted(
                relationships.values(),
                key=lambda item: (item.relationship_kind.value, item.repository_rel_path),
            )
        )

    def _primary_component_for_file(self, repository_rel_path: str, owner_id: str):
        component_id = self._repository._build_component_context_resolver().primary_component_id_for_file(
            repository_rel_path,
            owner_id,
        )
        if component_id is None:
            return None
        for component in self._repository.arch.get_components():
            if component.id == component_id:
                return component
        raise ValueError(f"resolved primary component does not exist: `{component_id}`")

    @staticmethod
    def _merge_provenance(*groups: tuple[ProvenanceEntry, ...]) -> tuple[ProvenanceEntry, ...]:
        merged: list[ProvenanceEntry] = []
        for group in groups:
            for entry in group:
                if entry not in merged:
                    merged.append(entry)
        return tuple(merged)

    @staticmethod
    def _projected_relationship(
        *,
        source_path: str,
        target_path: str,
        relationship_kind: FileRelationshipKind,
        target_component_name: str,
        provenance: tuple[ProvenanceEntry, ...],
    ) -> FileRelationshipRef:
        direction = "imported component artifact files" if relationship_kind == FileRelationshipKind.IMPORTS else "dependent component artifact files"
        projected = derived_summary_provenance(
            source_kind=SourceKind.DEPENDENCY_GRAPH,
            source_tool=preferred_source_tool(provenance),
            evidence_summary=(
                f"derived from component dependency graph and projected to {direction} for `{target_component_name}`"
            ),
            evidence_paths=merge_provenance_paths((*provenance,))[0:10] if provenance else (source_path, target_path),
        )
        return FileRelationshipRef(
            repository_rel_path=target_path,
            relationship_kind=relationship_kind,
            provenance=(*provenance, projected),
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.repository import Repository
