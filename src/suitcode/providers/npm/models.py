from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.models import ComponentKind, ProgrammingLanguage, TestFramework
from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.shared.package_json.models import PackageJsonManifest, PackageJsonWorkspacePackage


@dataclass(frozen=True)
class NpmPackageAnalysis:
    package_name: str
    package_path: str
    manifest_path: str
    component_kind: ComponentKind
    language: ProgrammingLanguage
    source_roots: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    local_dependencies: tuple[str, ...]
    external_dependencies: tuple[str, ...]
    manifest: PackageJsonManifest


@dataclass(frozen=True)
class NpmAggregatorAnalysis:
    package_name: str
    package_path: str
    manifest_path: str


@dataclass(frozen=True)
class NpmRunnerAnalysis:
    package_name: str
    package_path: str
    script_name: str
    command: str
    executable: str
    argv: tuple[str, ...]
    cwd: str
    referenced_files: tuple[str, ...]


@dataclass(frozen=True)
class NpmTestAnalysis:
    package_name: str
    package_path: str
    framework: TestFramework
    test_files: tuple[str, ...]
    discovery_method: TestDiscoveryMethod
    discovery_tool: str | None
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class NpmPackageManagerAnalysis:
    node_id: str
    display_name: str
    manager: str
    config_path: str | None
    owned_files: tuple[str, ...]


@dataclass(frozen=True)
class NpmExternalPackageAnalysis:
    package_name: str
    version_spec: str
    manager_id: str
    evidence_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class NpmOwnedFileAnalysis:
    repository_rel_path: str
    owner_id: str
    language: ProgrammingLanguage | None


@dataclass(frozen=True)
class NpmWorkspaceModel:
    packages: tuple[PackageJsonWorkspacePackage, ...]
    root_manifest: PackageJsonManifest
    workspace_package_names: frozenset[str]
