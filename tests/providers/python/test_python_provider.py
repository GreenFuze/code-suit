from __future__ import annotations

from suitcode.core.models import Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition as SuitTestDefinition
from suitcode.core.intelligence_models import DependencyRef
from suitcode.core.repository import Repository
from suitcode.core.tests.models import RelatedTestTarget, TestDiscoveryMethod
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.python import PythonProvider
from suitcode.providers.python.models import (
    PythonOwnedFileAnalysis,
    PythonPackageComponentAnalysis,
    PythonPackageManagerAnalysis,
    PythonRunnerAnalysis,
)
from suitcode.providers.python.symbol_models import PythonWorkspaceSymbol
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.providers.quality_provider_base import QualityProviderBase
from tests.providers.python.expected_python_provider_data import (
    EXPECTED_COMPONENT_IDS,
    EXPECTED_EXTERNAL_PACKAGE_IDS,
    EXPECTED_EXTERNAL_VERSION_SPECS,
    EXPECTED_PACKAGE_MANAGER_IDS,
    EXPECTED_REPRESENTATIVE_FILE_OWNERS,
    EXPECTED_RUNNER_IDS,
    EXPECTED_TEST_FILES,
    EXPECTED_TEST_IDS,
)


class _FakeSymbolService:
    def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[PythonWorkspaceSymbol, ...]:
        return (
            PythonWorkspaceSymbol(
                name='RepositoryManager',
                kind='class',
                repository_rel_path='src/acme/core/repository.py',
                line_start=1,
                line_end=7,
                column_start=1,
                column_end=30,
                container_name=None,
                signature=None,
            ),
        )


def test_python_provider_implements_all_provider_contracts() -> None:
    assert issubclass(PythonProvider, ArchitectureProviderBase)
    assert issubclass(PythonProvider, CodeProviderBase)
    assert issubclass(PythonProvider, TestProviderBase)
    assert issubclass(PythonProvider, QualityProviderBase)


def test_python_provider_returns_top_level_package_components_only(python_provider: PythonProvider) -> None:
    components = python_provider.get_components()

    assert all(isinstance(item, Component) for item in components)
    assert {item.id for item in components} == EXPECTED_COMPONENT_IDS


def test_python_provider_returns_explicit_runners_only(python_provider: PythonProvider) -> None:
    runners = python_provider.get_runners()
    aggregators = python_provider.get_aggregators()

    assert all(isinstance(item, Runner) for item in runners)
    assert tuple(item.id for item in runners) == EXPECTED_RUNNER_IDS
    assert aggregators == tuple()


def test_python_provider_returns_package_manager_external_packages_tests_and_files(python_provider: PythonProvider) -> None:
    package_managers = python_provider.get_package_managers()
    external_packages = python_provider.get_external_packages()
    tests = python_provider.get_tests()
    discovered_tests = python_provider.get_discovered_tests()
    files = python_provider.get_files()

    assert all(isinstance(item, PackageManager) for item in package_managers)
    assert tuple(item.id for item in package_managers) == EXPECTED_PACKAGE_MANAGER_IDS

    assert all(isinstance(item, ExternalPackage) for item in external_packages)
    assert {item.id for item in external_packages} == EXPECTED_EXTERNAL_PACKAGE_IDS
    assert {item.id: item.version_spec for item in external_packages} == EXPECTED_EXTERNAL_VERSION_SPECS

    assert all(isinstance(item, SuitTestDefinition) for item in tests)
    assert tuple(item.id for item in tests) == EXPECTED_TEST_IDS
    assert {item.id: item.test_files for item in tests} == EXPECTED_TEST_FILES
    assert tuple(item.test_definition.id for item in discovered_tests) == EXPECTED_TEST_IDS
    assert discovered_tests[0].discovery_method in {
        TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT,
        TestDiscoveryMethod.HEURISTIC_CONFIG_GLOB,
    }
    assert discovered_tests[1].discovery_method == TestDiscoveryMethod.HEURISTIC_UNITTEST

    assert all(isinstance(item, FileInfo) for item in files)
    owners = {item.repository_rel_path: item.owner_id for item in files}
    assert {path: owners[path] for path in EXPECTED_REPRESENTATIVE_FILE_OWNERS} == EXPECTED_REPRESENTATIVE_FILE_OWNERS


def test_python_provider_internal_analysis_stays_python_specific(python_provider: PythonProvider) -> None:
    assert all(isinstance(item, PythonPackageComponentAnalysis) for item in python_provider._get_components())
    assert all(isinstance(item, PythonRunnerAnalysis) for item in python_provider._get_runners())
    assert all(isinstance(item, PythonPackageManagerAnalysis) for item in python_provider._get_package_managers())
    assert all(isinstance(item, PythonOwnedFileAnalysis) for item in python_provider._get_files())


def test_python_provider_get_symbol_translates_python_symbols(python_provider: PythonProvider) -> None:
    python_provider._symbol_service = _FakeSymbolService()

    symbols = python_provider.get_symbol('RepositoryManager')

    assert all(isinstance(item, EntityInfo) for item in symbols)
    assert symbols[0].name == 'RepositoryManager'
    assert symbols[0].repository_rel_path == 'src/acme/core/repository.py'


def test_repository_intelligence_wraps_registered_python_provider(python_repository: Repository) -> None:
    assert python_repository.provider_ids == ('python',)
    assert {item.id for item in python_repository.arch.get_components()} == EXPECTED_COMPONENT_IDS
    assert tuple(item.id for item in python_repository.arch.get_runners()) == EXPECTED_RUNNER_IDS
    assert tuple(item.id for item in python_repository.tests.get_tests()) == EXPECTED_TEST_IDS
    assert python_repository.quality.provider_ids == ('python',)


def test_repository_related_tests_for_python_component_file(python_repository: Repository) -> None:
    matches = python_repository.tests.get_related_tests(
        RelatedTestTarget(repository_rel_path='src/acme/core/repository.py')
    )

    assert tuple(match.test_definition.id for match in matches) == EXPECTED_TEST_IDS
    assert all(match.relation_reason == 'same_component' for match in matches)


def test_python_provider_returns_declared_component_dependencies_only(python_provider: PythonProvider) -> None:
    dependencies = python_provider.get_component_dependencies("component:python:acme")
    dependents = python_provider.get_component_dependents("component:python:acme")

    assert all(isinstance(item, DependencyRef) for item in dependencies)
    assert {item.target_id for item in dependencies} == EXPECTED_EXTERNAL_PACKAGE_IDS
    assert all(item.dependency_scope == "declared" for item in dependencies)
    assert dependents == tuple()

