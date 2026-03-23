from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.models import ComponentKind, ProgrammingLanguage


@dataclass(frozen=True)
class GoPackageAnalysis:
    module_root_rel_path: str
    import_path: str
    package_name: str
    directory_rel_path: str
    component_kind: ComponentKind
    source_roots: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    go_files: tuple[str, ...]
    test_files: tuple[str, ...]
    imports: tuple[str, ...]
    is_main: bool


@dataclass(frozen=True)
class GoPackageManagerAnalysis:
    node_id: str
    module_root_rel_path: str
    display_name: str
    manager: str
    config_path: str | None
    owned_files: tuple[str, ...]


@dataclass(frozen=True)
class GoExternalPackageAnalysis:
    external_package_id: str
    package_name: str
    version_spec: str
    manager_id: str
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class GoOwnedFileAnalysis:
    repository_rel_path: str
    owner_id: str
    language: ProgrammingLanguage | None


@dataclass(frozen=True)
class GoTestAnalysis:
    test_id: str
    name: str
    import_path: str
    module_root_rel_path: str
    test_files: tuple[str, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class GoModuleAnalysis:
    module_root_rel_path: str
    module_path: str
    components: tuple[GoPackageAnalysis, ...]
    package_manager: GoPackageManagerAnalysis
    external_packages: tuple[GoExternalPackageAnalysis, ...]
    files: tuple[GoOwnedFileAnalysis, ...]


@dataclass(frozen=True)
class GoWorkspaceAnalysis:
    module_roots_rel_path: tuple[str, ...]
    modules: tuple[GoModuleAnalysis, ...]
    components: tuple[GoPackageAnalysis, ...]
    package_managers: tuple[GoPackageManagerAnalysis, ...]
    external_packages: tuple[GoExternalPackageAnalysis, ...]
    files: tuple[GoOwnedFileAnalysis, ...]
