from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.models import ComponentKind, ProgrammingLanguage
from suitcode.providers.shared.pyproject.models import PyProjectManifest


@dataclass(frozen=True)
class PythonPackageComponentAnalysis:
    package_name: str
    package_path: str
    component_kind: ComponentKind
    source_roots: tuple[str, ...]
    artifact_paths: tuple[str, ...]


@dataclass(frozen=True)
class PythonRunnerAnalysis:
    script_name: str
    entrypoint: str
    argv: tuple[str, ...]
    cwd: str | None
    referenced_files: tuple[str, ...]


@dataclass(frozen=True)
class PythonPackageManagerAnalysis:
    node_id: str
    display_name: str
    manager: str
    config_path: str | None
    owned_files: tuple[str, ...]


@dataclass(frozen=True)
class PythonExternalPackageAnalysis:
    package_name: str
    version_spec: str
    manager_id: str


@dataclass(frozen=True)
class PythonOwnedFileAnalysis:
    repository_rel_path: str
    owner_id: str
    language: ProgrammingLanguage | None


@dataclass(frozen=True)
class PythonWorkspaceModel:
    manifest: PyProjectManifest
    components: tuple[PythonPackageComponentAnalysis, ...]
