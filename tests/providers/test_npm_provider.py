from __future__ import annotations

from suitcode.core.models import (
    Aggregator,
    Component,
    EntityInfo,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition as DefinitionNode,
)
from suitcode.core.tests.models import RelatedTestTarget
from suitcode.core.repository import Repository
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.npm import NPMProvider
from suitcode.providers.npm.quality_models import NpmQualityEntityDelta, NpmQualityOperationResult
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.providers.quality_models import QualityFileResult
from suitcode.providers.quality_provider_base import QualityProviderBase
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol
from tests.providers.npm.expected_npm_provider_data import (
    EXPECTED_AGGREGATOR_IDS,
    EXPECTED_COMPONENT_IDS,
    EXPECTED_COMPONENT_KINDS,
    EXPECTED_COMPONENT_LANGUAGES,
    EXPECTED_EXTERNAL_PACKAGE_IDS,
    EXPECTED_PACKAGE_MANAGER_IDS,
    EXPECTED_REPRESENTATIVE_FILE_OWNERS,
    EXPECTED_TEST_IDS,
)


def test_architecture_provider_base_contract() -> None:
    assert issubclass(NPMProvider, ArchitectureProviderBase)


def test_code_provider_base_contract() -> None:
    assert issubclass(NPMProvider, CodeProviderBase)


def test_test_provider_base_contract() -> None:
    assert issubclass(NPMProvider, TestProviderBase)


def test_quality_provider_base_contract() -> None:
    assert issubclass(NPMProvider, QualityProviderBase)


def test_npm_provider_returns_monorepo_components(npm_provider: NPMProvider) -> None:
    components = npm_provider.get_components()
    component_ids = {component.id for component in components}
    component_languages = {
        component.id: component.language.value
        for component in components
        if component.id in EXPECTED_COMPONENT_LANGUAGES
    }
    component_kinds = {
        component.id: component.component_kind.value
        for component in components
        if component.id in EXPECTED_COMPONENT_KINDS
    }

    assert isinstance(components[0], Component)
    assert component_ids == EXPECTED_COMPONENT_IDS
    assert component_languages == EXPECTED_COMPONENT_LANGUAGES
    assert component_kinds == EXPECTED_COMPONENT_KINDS


def test_npm_provider_returns_aggregators_runners_and_tests(npm_provider: NPMProvider) -> None:
    aggregators = npm_provider.get_aggregators()
    runners = npm_provider.get_runners()
    tests = npm_provider.get_tests()

    assert all(isinstance(node, Aggregator) for node in aggregators)
    assert {node.id for node in aggregators} == EXPECTED_AGGREGATOR_IDS
    assert any(node.id == "runner:npm:@monorepo/codegen:build" for node in runners)
    assert any(node.id == "runner:npm:@monorepo/codegen:test" for node in runners)
    assert {node.id for node in tests} == EXPECTED_TEST_IDS
    assert all(isinstance(node, Runner) for node in runners)
    assert all(isinstance(node, DefinitionNode) for node in tests)


def test_npm_provider_returns_package_managers_external_packages_and_files(npm_provider: NPMProvider) -> None:
    package_managers = npm_provider.get_package_managers()
    external_packages = npm_provider.get_external_packages()
    files = npm_provider.get_files()

    assert all(isinstance(node, PackageManager) for node in package_managers)
    assert tuple(node.id for node in package_managers) == EXPECTED_PACKAGE_MANAGER_IDS
    assert all(isinstance(node, ExternalPackage) for node in external_packages)
    assert {node.id for node in external_packages} == EXPECTED_EXTERNAL_PACKAGE_IDS
    assert all(node.manager_id == "pkgmgr:npm:root" for node in external_packages)

    assert all(isinstance(node, FileInfo) for node in files)
    owned = {node.repository_rel_path: node.owner_id for node in files}
    assert {path: owned[path] for path in EXPECTED_REPRESENTATIVE_FILE_OWNERS} == EXPECTED_REPRESENTATIVE_FILE_OWNERS


def test_npm_provider_internal_analysis_stays_npm_specific(npm_provider: NPMProvider) -> None:
    assert all(isinstance(item, NpmPackageAnalysis) for item in npm_provider._get_components())
    assert all(isinstance(item, NpmAggregatorAnalysis) for item in npm_provider._get_aggregators())
    assert all(isinstance(item, NpmRunnerAnalysis) for item in npm_provider._get_runners())
    assert all(isinstance(item, NpmTestAnalysis) for item in npm_provider._get_tests())
    assert all(isinstance(item, NpmPackageManagerAnalysis) for item in npm_provider._get_package_managers())
    assert all(isinstance(item, NpmOwnedFileAnalysis) for item in npm_provider._get_files())


def test_npm_provider_uses_fixture_repository_root(npm_repository: Repository) -> None:
    assert npm_repository.root.name == "npm"
    assert npm_repository.provider_ids == ("npm",)


def test_npm_provider_get_symbol_returns_entity_info(npm_provider: NPMProvider) -> None:

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="CoreContainer",
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[assignment]
    symbols = npm_provider.get_symbol("Core")

    assert len(symbols) == 1
    assert isinstance(symbols[0], EntityInfo)
    assert symbols[0].id == "entity:packages/core/src/index.ts:class:Core:1-11"
    assert symbols[0].signature == "CoreContainer"


def test_npm_provider_internal_symbol_analysis_stays_npm_specific(npm_provider: NPMProvider) -> None:

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature=None,
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[assignment]

    assert all(isinstance(item, NpmWorkspaceSymbol) for item in npm_provider._get_symbols("Core"))


def test_npm_provider_quality_methods_return_public_results(npm_provider: NPMProvider) -> None:
    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=True,
                success=True,
                message="linted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="after",
            )

        def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="prettier",
                operation="format",
                changed=False,
                success=True,
                message="formatted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=False,
                content_sha_before="same",
                content_sha_after="same",
            )

    npm_provider._quality_service = _FakeQualityService()  # type: ignore[assignment]

    lint_result = npm_provider.lint_file("packages/core/src/index.ts", is_fix=True)
    format_result = npm_provider.format_file("packages/core/src/index.ts")

    assert isinstance(lint_result, QualityFileResult)
    assert isinstance(format_result, QualityFileResult)
    assert lint_result.tool == "eslint"
    assert format_result.tool == "prettier"


def test_repository_intelligence_wraps_registered_npm_provider(npm_repository: Repository) -> None:
    component_ids = {component.id for component in npm_repository.arch.get_components()}
    test_ids = {test.id for test in npm_repository.tests.get_tests()}

    assert component_ids == EXPECTED_COMPONENT_IDS
    assert test_ids == EXPECTED_TEST_IDS
    assert npm_repository.quality.provider_ids == ("npm",)


def test_repository_code_intelligence_uses_registered_provider(npm_repository: Repository) -> None:
    npm_provider = npm_repository.get_provider("npm")

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False) -> tuple[NpmWorkspaceSymbol, ...]:
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=11,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="CoreContainer",
                ),
            )

    npm_provider._symbol_service = _FakeSymbolService()  # type: ignore[attr-defined]
    symbols = npm_repository.code.get_symbol("Core")

    assert len(symbols) == 1
    assert symbols[0].id == "entity:packages/core/src/index.ts:class:Core:1-11"


def test_repository_quality_intelligence_dispatches_to_selected_provider(npm_repository: Repository) -> None:
    npm_provider = npm_repository.get_provider("npm")

    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=True,
                success=True,
                message="linted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="after",
            )

        def format_file(self, repository_rel_path: str) -> NpmQualityOperationResult:
            return NpmQualityOperationResult(
                repository_rel_path=repository_rel_path,
                tool="prettier",
                operation="format",
                changed=False,
                success=True,
                message="formatted",
                diagnostics=tuple(),
                entity_delta=NpmQualityEntityDelta(),
                applied_fixes=False,
                content_sha_before="same",
                content_sha_after="same",
            )

    npm_provider._quality_service = _FakeQualityService()  # type: ignore[attr-defined]

    lint_result = npm_repository.quality.lint_file("packages/core/src/index.ts", is_fix=True, provider_id="npm")
    format_result = npm_repository.quality.format_file("packages/core/src/index.ts", provider_id="npm")

    assert lint_result.tool == "eslint"
    assert format_result.tool == "prettier"


def test_repository_file_owner_and_files_by_owner(npm_repository: Repository) -> None:
    file_owner = npm_repository.get_file_owner("packages/core/src/index.ts")
    files = npm_repository.list_files_by_owner("component:npm:@monorepo/core")

    assert file_owner.owner.id == "component:npm:@monorepo/core"
    assert any(item.repository_rel_path == "packages/core/src/index.ts" for item in files)


def test_repository_related_tests_for_npm_component_file(npm_repository: Repository) -> None:
    matches = npm_repository.tests.get_related_tests(
        RelatedTestTarget(repository_rel_path="packages/core/src/index.ts")
    )

    assert any(match.test_definition.id == "test:npm:@monorepo/core" for match in matches)
    assert all(match.relation_reason == "same_package" for match in matches)
