from __future__ import annotations

from pathlib import Path

from suitcode.core.intelligence_models import DependencyRef
from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
from suitcode.core.models import Aggregator, Component, ExternalPackage, FileInfo, PackageManager, Runner
from suitcode.core.models.graph_types import ComponentKind, NodeKind, ProgrammingLanguage
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.provider_roles import ProviderRole


class _FakeRepository:
    def __init__(self, providers):
        self._providers = providers

    def get_providers_for_role(self, role: ProviderRole):
        if role == ProviderRole.ARCHITECTURE:
            return self._providers
        return tuple()


class _ArchitectureProvider(ArchitectureProviderBase):
    PROVIDER_ID = "fake-arch"
    DISPLAY_NAME = "fake-arch"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.ARCHITECTURE})

    def __init__(self, repository, suffix: str) -> None:
        super().__init__(repository)
        self._suffix = suffix

    def get_components(self):
        return (
            Component(
                id=f"component:{self._suffix}",
                name=f"component-{self._suffix}",
                component_kind=ComponentKind.PACKAGE,
                language=ProgrammingLanguage.TYPESCRIPT,
            ),
        )

    def get_aggregators(self):
        return (Aggregator(id=f"aggregator:{self._suffix}", name=f"aggregator-{self._suffix}"),)

    def get_runners(self):
        return (Runner(id=f"runner:{self._suffix}", name=f"runner-{self._suffix}", argv=("echo", self._suffix)),)

    def get_package_managers(self):
        return (PackageManager(id=f"pkg:{self._suffix}", name=f"pkg-{self._suffix}", manager="fake"),)

    def get_external_packages(self):
        return (ExternalPackage(id=f"ext:{self._suffix}", name=f"ext-{self._suffix}", manager_id="pkg"),)

    def get_files(self):
        return (
            FileInfo(
                id=f"file:{self._suffix}",
                name=f"file-{self._suffix}",
                repository_rel_path=f"{self._suffix}.ts",
                language=ProgrammingLanguage.TYPESCRIPT,
                owner_id=f"component:{self._suffix}",
            ),
        )

    def get_component_dependencies(self, component_id: str):
        if component_id != f"component:{self._suffix}":
            return tuple()
        return (
            DependencyRef(
                target_id=f"ext:{self._suffix}",
                target_kind="external_package",
                dependency_scope="runtime",
            ),
        )

    def get_component_dependents(self, component_id: str):
        if component_id != f"component:{self._suffix}":
            return tuple()
        return (f"component:{self._suffix}:dependent",)


def test_architecture_intelligence_concatenates_and_sorts_results() -> None:
    repo = _FakeRepository(
        (
            _ArchitectureProvider(repository=None, suffix="b"),  # type: ignore[arg-type]
            _ArchitectureProvider(repository=None, suffix="a"),  # type: ignore[arg-type]
        )
    )
    intelligence = ArchitectureIntelligence(repo)  # type: ignore[arg-type]

    assert tuple(node.id for node in intelligence.get_components()) == ("component:a", "component:b")
    assert tuple(node.id for node in intelligence.get_aggregators()) == ("aggregator:a", "aggregator:b")
    assert tuple(node.id for node in intelligence.get_runners()) == ("runner:a", "runner:b")
    assert tuple(node.id for node in intelligence.get_package_managers()) == ("pkg:a", "pkg:b")
    assert tuple(node.id for node in intelligence.get_external_packages()) == ("ext:a", "ext:b")
    assert tuple(node.id for node in intelligence.get_files()) == ("file:a", "file:b")


def test_architecture_intelligence_routes_dependency_queries_to_component_owner() -> None:
    repo = _FakeRepository((_ArchitectureProvider(repository=None, suffix="a"),))  # type: ignore[arg-type]
    intelligence = ArchitectureIntelligence(repo)  # type: ignore[arg-type]

    dependencies = intelligence.get_component_dependencies("component:a")
    dependents = intelligence.get_component_dependents("component:a")

    assert dependencies[0].target_id == "ext:a"
    assert dependents == ("component:a:dependent",)
