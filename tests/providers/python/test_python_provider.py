from __future__ import annotations

from suitcode.core.action_models import ActionKind
from suitcode.core.runner_service import RunnerService
from suitcode.core.models import Component, EntityInfo, ExternalPackage, FileInfo, PackageManager, Runner, TestDefinition as SuitTestDefinition
from suitcode.core.intelligence_models import DependencyRef
from suitcode.core.repository import Repository
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import heuristic_provenance
from suitcode.core.tests.models import (
    RelatedTestTarget,
    TestExecutionResult as CoreTestExecutionResult,
    TestExecutionStatus as CoreTestExecutionStatus,
)
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.python import PythonProvider
from suitcode.providers.shared.action_execution import ActionExecutionResult, ActionExecutionStatus
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
    assert issubclass(PythonProvider, ActionProviderBase)
    assert issubclass(PythonProvider, CodeProviderBase)
    assert issubclass(PythonProvider, TestProviderBase)
    assert issubclass(PythonProvider, QualityProviderBase)


def test_python_provider_returns_top_level_package_components_only(python_provider: PythonProvider) -> None:
    components = python_provider.get_components()

    assert all(isinstance(item, Component) for item in components)
    assert {item.id for item in components} == EXPECTED_COMPONENT_IDS
    assert all(item.provenance for item in components)
    assert all(item.provenance[0].source_kind.value == "manifest" for item in components)


def test_python_provider_returns_explicit_runners_only(python_provider: PythonProvider) -> None:
    runners = python_provider.get_runners()
    aggregators = python_provider.get_aggregators()

    assert all(isinstance(item, Runner) for item in runners)
    assert tuple(item.id for item in runners) == EXPECTED_RUNNER_IDS
    assert all(item.provenance for item in runners)
    assert aggregators == tuple()


def test_python_provider_returns_package_manager_external_packages_tests_and_files(python_provider: PythonProvider) -> None:
    package_managers = python_provider.get_package_managers()
    external_packages = python_provider.get_external_packages()
    tests = python_provider.get_tests()
    discovered_tests = python_provider.get_discovered_tests()
    files = python_provider.get_files()

    assert all(isinstance(item, PackageManager) for item in package_managers)
    assert tuple(item.id for item in package_managers) == EXPECTED_PACKAGE_MANAGER_IDS
    assert all(item.provenance for item in package_managers)

    assert all(isinstance(item, ExternalPackage) for item in external_packages)
    assert {item.id for item in external_packages} == EXPECTED_EXTERNAL_PACKAGE_IDS
    assert {item.id: item.version_spec for item in external_packages} == EXPECTED_EXTERNAL_VERSION_SPECS
    assert all(item.provenance for item in external_packages)

    assert all(isinstance(item, SuitTestDefinition) for item in tests)
    assert tuple(item.id for item in tests) == EXPECTED_TEST_IDS
    assert {item.id: item.test_files for item in tests} == EXPECTED_TEST_FILES
    assert all(item.provenance for item in tests)
    assert tuple(item.test_definition.id for item in discovered_tests) == EXPECTED_TEST_IDS
    assert discovered_tests[0].primary_source_kind in {SourceKind.TEST_TOOL, SourceKind.HEURISTIC}
    assert discovered_tests[1].primary_source_kind == SourceKind.HEURISTIC
    assert discovered_tests[0].primary_source_tool in {"pytest", None}
    assert discovered_tests[1].primary_source_tool is None

    assert all(isinstance(item, FileInfo) for item in files)
    assert all(item.provenance for item in files)
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
    assert symbols[0].provenance[0].source_kind.value == "lsp"


def test_python_provider_definition_and_reference_locations_include_provenance(python_provider: PythonProvider) -> None:
    class _FakeFileSymbolService:
        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("src/acme/core/repository.py", 1, 7, 1, 30),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (("src/acme/core/repository.py", 5, 7, 1, 12),)

    python_provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[assignment]

    definitions = python_provider.find_definition("src/acme/core/repository.py", 1, 1)
    references = python_provider.find_references("src/acme/core/repository.py", 1, 1)

    assert definitions[0].provenance[0].source_kind.value == "lsp"
    assert definitions[0].provenance[0].source_tool == "basedpyright"
    assert references[0].provenance[0].source_kind.value == "lsp"
    assert references[0].provenance[0].source_tool == "basedpyright"


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


def test_python_provider_exposes_deterministic_actions(python_provider: PythonProvider) -> None:
    actions = python_provider.get_actions()

    assert actions
    assert all(item.provider_id == "python" for item in actions)
    assert all(item.invocation.argv for item in actions)
    assert all(item.provenance for item in actions)
    assert any(item.kind == ActionKind.RUNNER_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.TEST_EXECUTION for item in actions)
    assert any(item.kind == ActionKind.BUILD_EXECUTION for item in actions)


def test_python_provider_describe_and_run_test_targets(python_provider: PythonProvider) -> None:
    description = python_provider.describe_test_target("test:python:pytest:root")

    assert description.test_definition.id == "test:python:pytest:root"
    assert description.command_argv
    assert description.provenance

    class _FakeExecutionService:
        def run_target(self, target_description, timeout_seconds: int):
            return CoreTestExecutionResult(
                test_id=target_description.test_definition.id,
                status=CoreTestExecutionStatus.PASSED,
                success=True,
                command_argv=target_description.command_argv,
                command_cwd=target_description.command_cwd,
                exit_code=0,
                duration_ms=timeout_seconds,
                log_path=".suit/runs/tests/fake.log",
                warning=target_description.warning,
                output_excerpt="ok",
                provenance=(
                    heuristic_provenance(
                        evidence_summary="fake execution result",
                        evidence_paths=("tests/test_basic.py",),
                    ),
                ),
            )

    python_provider._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
    results = python_provider.run_test_targets(("test:python:pytest:root",), timeout_seconds=30)

    assert results[0].test_id == "test:python:pytest:root"
    assert results[0].duration_ms == 30
    assert results[0].warning == description.warning


def test_python_repository_describe_and_run_runner(python_repository: Repository) -> None:
    runner_id = python_repository.arch.get_runners()[0].id
    context = python_repository.describe_runner(runner_id)

    assert context.runner.id == runner_id
    assert context.action_id
    assert context.provenance

    class _FakeActionExecutionService:
        def run(
            self,
            *,
            action_id: str,
            command_argv: tuple[str, ...],
            command_cwd: str | None,
            timeout_seconds: int,
            run_group: str,
        ) -> ActionExecutionResult:
            return ActionExecutionResult(
                action_id=action_id,
                status=ActionExecutionStatus.PASSED,
                success=True,
                command_argv=command_argv,
                command_cwd=command_cwd,
                exit_code=0,
                duration_ms=timeout_seconds,
                log_path=".suit/runs/runners/fake.log",
                output_excerpt="ok",
                output="ok",
            )

    python_repository._runner_service = RunnerService(  # type: ignore[attr-defined]
        python_repository,
        action_execution_service=_FakeActionExecutionService(),
    )
    result = python_repository.run_runner(runner_id, timeout_seconds=9)

    assert result.runner_id == runner_id
    assert result.status.value == "passed"
    assert result.duration_ms == 9

