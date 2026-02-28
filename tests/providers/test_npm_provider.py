from __future__ import annotations

import shutil
from pathlib import Path

from suitcode.core.models import (
    Aggregator,
    Component,
    ExternalPackage,
    FileInfo,
    PackageManager,
    Runner,
    TestDefinition as DefinitionNode,
)
from suitcode.core.workspace import Workspace
from suitcode.providers.architecture_provider_base import ArchitectureProviderBase
from suitcode.providers.npm import NPMProvider
from suitcode.providers.npm.models import (
    NpmAggregatorAnalysis,
    NpmOwnedFileAnalysis,
    NpmPackageAnalysis,
    NpmPackageManagerAnalysis,
    NpmRunnerAnalysis,
    NpmTestAnalysis,
)


FIXTURE_ROOT = Path("tests/test_repos/npm")


def _provider(tmp_path: Path) -> NPMProvider:
    repo_root = tmp_path / "npm"
    shutil.copytree(FIXTURE_ROOT, repo_root)
    (repo_root / ".git").mkdir()
    workspace = Workspace(repo_root)
    return NPMProvider(workspace.repositories[0])


def test_architecture_provider_base_contract() -> None:
    assert issubclass(NPMProvider, ArchitectureProviderBase)


def test_npm_provider_returns_monorepo_components(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    components = provider.get_components()
    component_ids = {component.id for component in components}

    assert isinstance(components[0], Component)
    assert "component:npm:@monorepo/core" in component_ids
    assert "component:npm:@monorepo/auth-service" in component_ids
    assert "component:npm:@monorepo/native-addon" in component_ids
    assert "component:npm:@monorepo/build-aggregator" in component_ids
    assert "component:npm:@monorepo/codegen" in component_ids


def test_npm_provider_returns_aggregators_runners_and_tests(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    aggregators = provider.get_aggregators()
    runners = provider.get_runners()
    tests = provider.get_tests()

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


def test_npm_provider_returns_package_managers_external_packages_and_files(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    package_managers = provider.get_package_managers()
    external_packages = provider.get_external_packages()
    files = provider.get_files()

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


def test_npm_provider_internal_analysis_stays_npm_specific(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert all(isinstance(item, NpmPackageAnalysis) for item in provider._get_components())
    assert all(isinstance(item, NpmAggregatorAnalysis) for item in provider._get_aggregators())
    assert all(isinstance(item, NpmRunnerAnalysis) for item in provider._get_runners())
    assert all(isinstance(item, NpmTestAnalysis) for item in provider._get_tests())
    assert all(isinstance(item, NpmPackageManagerAnalysis) for item in provider._get_package_managers())
    assert all(isinstance(item, NpmOwnedFileAnalysis) for item in provider._get_files())
