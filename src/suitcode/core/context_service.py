from __future__ import annotations

from typing import TYPE_CHECKING

from suitcode.core.intelligence_models import ComponentContext, FileContext, SymbolContext
from suitcode.core.models import Component, EntityInfo
from suitcode.core.ownership_index import OwnershipIndex
from suitcode.core.tests.models import RelatedTestTarget

if TYPE_CHECKING:
    from suitcode.core.repository import Repository


class ContextService:
    def __init__(self, repository: Repository, ownership_index: OwnershipIndex) -> None:
        self._repository = repository
        self._ownership_index = ownership_index

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
                    runner_ids=self.related_runner_ids_for_component(component, owned_files),
                    related_test_ids=tuple(match.test_definition.id for match in related_tests[:test_preview_limit]),
                    dependency_count=len(dependencies),
                    dependencies_preview=dependencies[:dependency_preview_limit],
                    dependent_count=len(dependents),
                    dependents_preview=dependents[:dependent_preview_limit],
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
                )
            )
        return tuple(contexts)

    def describe_symbol_context(
        self,
        symbol_id: str,
        reference_preview_limit: int,
        test_preview_limit: int,
    ) -> SymbolContext:
        symbol = self.resolve_symbol(symbol_id)
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
        )

    def resolve_symbol(self, symbol_id: str) -> EntityInfo:
        if not symbol_id.startswith("entity:"):
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        parts = symbol_id.split(":")
        if len(parts) < 4:
            raise ValueError(f"unsupported symbol id format: `{symbol_id}`")
        repository_rel_path = parts[1]
        matches = [item for item in self._repository.code.list_symbols_in_file(repository_rel_path) if item.id == symbol_id]
        if not matches:
            raise ValueError(f"symbol id could not be resolved: `{symbol_id}`")
        if len(matches) > 1:
            raise ValueError(f"symbol id resolved ambiguously: `{symbol_id}`")
        return matches[0]

    def related_runner_ids_for_component(self, component: Component, owned_files: tuple[object, ...]) -> tuple[str, ...]:
        component_paths = {item.repository_rel_path for item in owned_files}
        runner_ids: list[str] = []
        for runner in self._repository.arch.get_runners():
            if runner.cwd and any(path == runner.cwd or path.startswith(f"{runner.cwd}/") for path in component_paths):
                runner_ids.append(runner.id)
                continue
            runner_files = self._ownership_index.files_for_owner(runner.id)
            if any(
                item.repository_rel_path in component_paths
                or item.repository_rel_path == source_root
                or item.repository_rel_path.startswith(f"{source_root}/")
                for item in runner_files
                for source_root in component.source_roots
            ):
                runner_ids.append(runner.id)
        return tuple(sorted(set(runner_ids)))

    @staticmethod
    def _validate_exact_batch(items: tuple[str, ...], field_name: str) -> None:
        if not items:
            raise ValueError(f"{field_name} must not be empty")
        if any(not item.strip() for item in items):
            raise ValueError(f"{field_name} must not contain empty values")
        if len(set(items)) != len(items):
            raise ValueError(f"{field_name} must not contain duplicates")
