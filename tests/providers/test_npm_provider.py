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
from suitcode.core.repository import Repository
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.code_provider_base import CodeProviderBase
from suitcode.providers.npm import NPMProvider
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)
from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol


def test_architecture_provider_base_contract() -> None:
    assert issubclass(NPMProvider, ArchitectureProviderBase)


def test_code_provider_base_contract() -> None:
    assert issubclass(NPMProvider, CodeProviderBase)


def test_test_provider_base_contract() -> None:
    assert issubclass(NPMProvider, TestProviderBase)


def test_npm_provider_returns_monorepo_components(npm_provider: NPMProvider) -> None:
    components = npm_provider.get_components()
    component_ids = {component.id for component in components}

    assert isinstance(components[0], Component)
    assert "component:npm:@monorepo/core" in component_ids
    assert "component:npm:@monorepo/auth-service" in component_ids
    assert "component:npm:@monorepo/native-addon" in component_ids
    assert "component:npm:@monorepo/build-aggregator" in component_ids
    assert "component:npm:@monorepo/codegen" in component_ids


def test_npm_provider_returns_aggregators_runners_and_tests(npm_provider: NPMProvider) -> None:
    aggregators = npm_provider.get_aggregators()
    runners = npm_provider.get_runners()
    tests = npm_provider.get_tests()

    assert all(isinstance(node, Aggregator) for node in aggregators)
    assert {node.id for node in aggregators} == {
        "aggregator:npm:@monorepo/build-all",
        "aggregator:npm:@monorepo/deploy-all",
        "aggregator:npm:@monorepo/test-all",
    }
    assert any(node.id == "runner:npm:@monorepo/codegen:build" for node in runners)
    assert any(node.id == "runner:npm:@monorepo/codegen:test" for node in runners)
    assert any(node.id == "test:npm:@monorepo/core" for node in tests)
    assert all(isinstance(node, Runner) for node in runners)
    assert all(isinstance(node, DefinitionNode) for node in tests)


def test_npm_provider_returns_package_managers_external_packages_and_files(npm_provider: NPMProvider) -> None:
    package_managers = npm_provider.get_package_managers()
    external_packages = npm_provider.get_external_packages()
    files = npm_provider.get_files()

    assert all(isinstance(node, PackageManager) for node in package_managers)
    assert [node.id for node in package_managers] == [
        "pkgmgr:cargo",
        "pkgmgr:go",
        "pkgmgr:npm:root",
        "pkgmgr:python",
    ]
    assert all(isinstance(node, ExternalPackage) for node in external_packages)
    assert any(node.id == "external:npm:typescript" for node in external_packages)
    assert any(node.id == "external:npm:jest" for node in external_packages)
    assert all(node.manager_id == "pkgmgr:npm:root" for node in external_packages)

    assert all(isinstance(node, FileInfo) for node in files)
    owned = {node.repository_rel_path: node.owner_id for node in files}
    assert owned["packages/core/src/index.ts"] == "component:npm:@monorepo/core"
    assert owned["packages/core/src/index.test.ts"] == "test:npm:@monorepo/core"
    assert owned["tools/codegen/main.py"] == "runner:npm:@monorepo/codegen:build"
    assert owned["package.json"] == "pkgmgr:npm:root"
    assert owned["tools/codegen/pyproject.toml"] == "pkgmgr:python"
    assert owned["modules/wasm-module/Cargo.toml"] == "pkgmgr:cargo"
    assert owned["modules/native-addon/go.mod"] == "pkgmgr:go"


def test_npm_provider_internal_analysis_stays_npm_specific(npm_provider: NPMProvider) -> None:
    assert all(isinstance(item, NpmPackageAnalysis) for item in npm_provider._get_components())
    assert all(isinstance(item, NpmAggregatorAnalysis) for item in npm_provider._get_aggregators())
    assert all(isinstance(item, NpmRunnerAnalysis) for item in npm_provider._get_runners())
    assert all(isinstance(item, NpmTestAnalysis) for item in npm_provider._get_tests())
    assert all(isinstance(item, NpmPackageManagerAnalysis) for item in npm_provider._get_package_managers())
    assert all(isinstance(item, NpmOwnedFileAnalysis) for item in npm_provider._get_files())


def test_npm_provider_uses_fixture_repository_root(npm_repository: Repository) -> None:
    assert npm_repository.root.name == "npm"


def test_npm_provider_get_symbol_returns_entity_info(npm_provider: NPMProvider) -> None:

    class _FakeSymbolService:
        def get_symbols(self, query: str) -> tuple[NpmWorkspaceSymbol, ...]:
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
        def get_symbols(self, query: str) -> tuple[NpmWorkspaceSymbol, ...]:
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
