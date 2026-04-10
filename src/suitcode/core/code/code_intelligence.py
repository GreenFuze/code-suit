from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.code.models import CodeLocation, SymbolLookupTarget
from suitcode.core.intelligence_models import (
    FileRelationshipKind,
    FileRelationshipRef,
    ImplementationFlowStepRef,
    InvariantFindingRef,
    RenderEdgeKind,
    RenderEdgeRef,
    StaticFlowEdgeRef,
)
from suitcode.core.models import EntityInfo, FileInfo
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.provenance import ProvenanceEntry, SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance
from suitcode.core.provenance_summary import merge_provenance_paths, preferred_source_tool
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import (
    CodeRuntimeCapabilities,
    RuntimeCapability,
    RuntimeCapabilityAvailability,
)


@dataclass(frozen=True)
class _ProviderSymbolCoverage:
    representative_file: str
    representative_symbol: EntityInfo
    has_workspace_match: bool
    has_definition: bool
    has_references: bool


class CodeIntelligence:
    def __init__(self, repository: "Repository") -> None:
        self._repository = repository
        self._runtime_capabilities_cache: tuple[CodeRuntimeCapabilities, ...] | None = None

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
        if self._runtime_capabilities_cache is None:
            self._runtime_capabilities_cache = tuple(
                self._verified_runtime_capabilities(provider) for provider in self.providers
            )
        return self._runtime_capabilities_cache

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

    def get_file_implementation_flow_steps(self, repository_rel_path: str) -> tuple[ImplementationFlowStepRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[str, int, int, str, str, str | None, str | None], ImplementationFlowStepRef] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_implementation_flow_steps(normalized_path)
            except ValueError:
                continue
            for item in items:
                key = (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.step_kind.value,
                    item.source_label,
                    item.target_label,
                    item.detail_label,
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
                key=lambda item: (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.step_kind.value,
                    item.source_label,
                    item.target_label or "",
                    item.detail_label or "",
                ),
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

    def get_file_invariant_findings(self, repository_rel_path: str) -> tuple[InvariantFindingRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[str, int, int, str, str], InvariantFindingRef] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_invariant_findings(normalized_path)
            except ValueError:
                continue
            for item in items:
                key = (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.field_name,
                    item.subject_label,
                )
                existing = merged.get(key)
                if existing is None:
                    merged[key] = item
                    continue
                merged_sites: list = []
                for site in (*existing.producer_sites_preview, *item.producer_sites_preview):
                    site_key = (site.repository_rel_path, site.line_start, site.column_start, site.label)
                    if any(
                        (current.repository_rel_path, current.line_start, current.column_start, current.label) == site_key
                        for current in merged_sites
                    ):
                        continue
                    merged_sites.append(site)
                merged[key] = item.model_copy(
                    update={
                        "producer_site_count": len(merged_sites),
                        "producer_sites_preview": tuple(merged_sites),
                        "provenance": tuple(dict.fromkeys((*existing.provenance, *item.provenance))),
                    }
                )
        return tuple(
            sorted(
                merged.values(),
                key=lambda item: (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.field_name,
                    item.subject_label,
                ),
            )
        )

    def get_file_local_flow_edges(self, repository_rel_path: str) -> tuple[StaticFlowEdgeRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        merged: dict[tuple[str, int, int, str, str, str], StaticFlowEdgeRef] = {}
        for provider in self._providers_for_file(normalized_path):
            try:
                items = provider.get_file_local_flow_edges(normalized_path)
            except ValueError:
                continue
            for item in items:
                key = (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.edge_kind.value,
                    item.source_label,
                    item.target_label,
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
                key=lambda item: (
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.edge_kind.value,
                    item.source_label,
                    item.target_label,
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
            matches = self._resolve_symbol_target_by_id_parts(symbol_id, repository_rel_path)
        if not matches:
            raise ValueError(f"symbol id could not be resolved: `{symbol_id}`")
        if len(matches) > 1:
            raise ValueError(f"symbol id resolved ambiguously: `{symbol_id}`")
        match = matches[0]
        if match.line_start is None or match.column_start is None:
            raise ValueError(f"symbol id has no usable location: `{symbol_id}`")
        return repository_rel_path, match.line_start, match.column_start

    def _resolve_symbol_target_by_id_parts(self, symbol_id: str, repository_rel_path: str) -> list[EntityInfo]:
        parts = symbol_id.split(":")
        if len(parts) < 5:
            return []
        entity_kind = parts[2]
        entity_name = parts[3]
        line_range = parts[4]
        line_range_parts = line_range.split("-", 1)
        if len(line_range_parts) != 2:
            return []
        try:
            line_start = int(line_range_parts[0])
        except ValueError:
            return []
        return [
            item
            for item in self.list_symbols_in_file(repository_rel_path)
            if item.entity_kind == entity_kind
            and item.name == entity_name
            and item.line_start == line_start
        ]

    def _providers_for_file(self, repository_rel_path: str) -> tuple[CodeProviderBase, ...]:
        return tuple(
            provider
            for provider in self._repository.get_providers_for_file_role(repository_rel_path, ProviderRole.CODE)
            if isinstance(provider, CodeProviderBase)
        )

    def _verified_runtime_capabilities(self, provider: CodeProviderBase) -> CodeRuntimeCapabilities:
        capabilities = provider.get_code_runtime_capabilities()
        if not any(
            capability.availability == RuntimeCapabilityAvailability.AVAILABLE
            for capability in (
                capabilities.symbol_search,
                capabilities.symbols_in_file,
                capabilities.definitions,
                capabilities.references,
                capabilities.implementations,
            )
        ):
            return capabilities
        coverage = self._provider_symbol_coverage(provider)
        if coverage is None:
            reason = (
                "provider-backed symbol coverage produced no symbols on representative owned files"
            )
            return CodeRuntimeCapabilities(
                symbol_search=self._degrade_runtime_capability(capabilities.symbol_search, reason),
                symbols_in_file=self._degrade_runtime_capability(capabilities.symbols_in_file, reason),
                definitions=self._degrade_runtime_capability(capabilities.definitions, reason),
                references=self._degrade_runtime_capability(capabilities.references, reason),
                implementations=self._degrade_runtime_capability(capabilities.implementations, reason),
            )
        return CodeRuntimeCapabilities(
            symbol_search=(
                capabilities.symbol_search
                if coverage.has_workspace_match
                else self._degrade_runtime_capability(
                    capabilities.symbol_search,
                    f"exact symbol search returned no provider-backed match for `{coverage.representative_symbol.name}`",
                )
            ),
            symbols_in_file=capabilities.symbols_in_file,
            definitions=(
                capabilities.definitions
                if coverage.has_definition
                else self._degrade_runtime_capability(
                    capabilities.definitions,
                    f"provider-backed definition lookup returned no result for `{coverage.representative_symbol.name}` in `{coverage.representative_file}`",
                )
            ),
            references=(
                capabilities.references
                if coverage.has_references
                else self._degrade_runtime_capability(
                    capabilities.references,
                    f"provider-backed reference lookup returned no result for `{coverage.representative_symbol.name}` in `{coverage.representative_file}`",
                )
            ),
            implementations=capabilities.implementations,
        )

    def _provider_symbol_coverage(self, provider: CodeProviderBase) -> _ProviderSymbolCoverage | None:
        first_symbol_coverage: _ProviderSymbolCoverage | None = None
        checked_workspace_symbols = 0
        for file_info in self._candidate_files_for_provider(provider):
            try:
                symbols = provider.list_symbols_in_file(file_info.repository_rel_path)
            except ValueError:
                continue
            if not symbols:
                continue
            for symbol in self._searchable_symbol_candidates(symbols):
                if symbol.line_start is None or symbol.column_start is None:
                    continue
                checked_workspace_symbols += 1
                if checked_workspace_symbols > 10:
                    return first_symbol_coverage
                has_workspace_match = self._provider_has_workspace_symbol_match(provider, symbol)
                if not has_workspace_match:
                    if first_symbol_coverage is None:
                        first_symbol_coverage = _ProviderSymbolCoverage(
                            representative_file=file_info.repository_rel_path,
                            representative_symbol=symbol,
                            has_workspace_match=False,
                            has_definition=False,
                            has_references=False,
                        )
                    continue
                has_definition = self._provider_has_definition(provider, file_info.repository_rel_path, symbol)
                has_references = self._provider_has_references(provider, file_info.repository_rel_path, symbol)
                return _ProviderSymbolCoverage(
                    representative_file=file_info.repository_rel_path,
                    representative_symbol=symbol,
                    has_workspace_match=has_workspace_match,
                    has_definition=has_definition,
                    has_references=has_references,
                )
        return first_symbol_coverage

    @classmethod
    def _searchable_symbol_candidates(cls, symbols: tuple[EntityInfo, ...]) -> tuple[EntityInfo, ...]:
        candidates = tuple(
            symbol
            for symbol in symbols
            if cls._is_searchable_symbol_name(symbol.name)
        )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    -int(item.name[:1].isupper()),
                    item.line_start or 10**9,
                    item.column_start or 10**9,
                    item.name,
                    item.id,
                ),
            )[:5]
        )

    @staticmethod
    def _is_searchable_symbol_name(name: str) -> bool:
        if not name:
            return False
        return all(character == "_" or character.isalnum() for character in name)

    def _provider_has_workspace_symbol_match(self, provider: CodeProviderBase, symbol: EntityInfo) -> bool:
        try:
            matches = provider.get_symbol(symbol.name, is_case_sensitive=True)
        except ValueError:
            return False
        return any(self._symbols_refer_to_same_anchor(item, symbol) for item in matches)

    @staticmethod
    def _symbols_refer_to_same_anchor(left: EntityInfo, right: EntityInfo) -> bool:
        if left.id == right.id:
            return True
        return (
            left.repository_rel_path == right.repository_rel_path
            and left.name == right.name
            and left.entity_kind == right.entity_kind
            and left.line_start == right.line_start
        )

    @staticmethod
    def _provider_has_definition(provider: CodeProviderBase, repository_rel_path: str, symbol: EntityInfo) -> bool:
        try:
            definitions = provider.find_definition(repository_rel_path, symbol.line_start, symbol.column_start)  # type: ignore[arg-type]
        except ValueError:
            return False
        return bool(definitions)

    @staticmethod
    def _provider_has_references(provider: CodeProviderBase, repository_rel_path: str, symbol: EntityInfo) -> bool:
        try:
            references = provider.find_references(
                repository_rel_path,
                symbol.line_start,  # type: ignore[arg-type]
                symbol.column_start,  # type: ignore[arg-type]
                include_definition=True,
            )
        except ValueError:
            return False
        return bool(references)

    def _candidate_files_for_provider(self, provider: CodeProviderBase) -> tuple[FileInfo, ...]:
        provider_id = provider.attachment.provider_id
        attachment_root_rel_path = provider.attachment.attachment_root_rel_path
        source_roots = self._component_source_roots_for_provider(provider_id)
        return tuple(
            sorted(
                (
                    file_info
                    for file_info in self._repository.arch.get_files()
                    if self._repository.provider_id_for_owner(file_info.owner_id) == provider_id
                    and self._attachment_contains_path(attachment_root_rel_path, file_info.repository_rel_path)
                    and (not source_roots or self._is_under_any_root(file_info.repository_rel_path, source_roots))
                ),
                key=lambda item: item.repository_rel_path,
            )
        )

    def _component_source_roots_for_provider(self, provider_id: str) -> frozenset[str]:
        roots: set[str] = set()
        for component in self._repository.arch.get_components():
            try:
                component_provider_id = self._repository.provider_id_for_owner(component.id)
            except ValueError:
                continue
            if component_provider_id != provider_id:
                continue
            roots.update(root for root in component.source_roots if root)
        return frozenset(roots)

    @staticmethod
    def _is_under_any_root(repository_rel_path: str, roots: frozenset[str]) -> bool:
        normalized_path = repository_rel_path.strip().strip("/").replace("\\", "/")
        for root in roots:
            normalized_root = root.strip().strip("/").replace("\\", "/")
            if not normalized_root:
                continue
            if normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}/"):
                return True
        return False

    @staticmethod
    def _attachment_contains_path(attachment_root_rel_path: str, repository_rel_path: str) -> bool:
        attachment_root = attachment_root_rel_path.strip().strip("/").replace("\\", "/")
        normalized_path = repository_rel_path.strip().strip("/").replace("\\", "/")
        if not attachment_root or attachment_root == ".":
            return True
        return normalized_path == attachment_root or normalized_path.startswith(f"{attachment_root}/")

    @staticmethod
    def _degrade_runtime_capability(capability: RuntimeCapability, reason: str) -> RuntimeCapability:
        if capability.availability != RuntimeCapabilityAvailability.AVAILABLE:
            return capability
        return capability.model_copy(
            update={
                "availability": RuntimeCapabilityAvailability.DEGRADED,
                "reason": reason,
            }
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
