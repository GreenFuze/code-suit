from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageJsonDependencySet:
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    peer_dependencies: dict[str, str]
    optional_dependencies: dict[str, str]

    def all_dependency_names(self) -> tuple[str, ...]:
        names = set(self.dependencies)
        names.update(self.dev_dependencies)
        names.update(self.peer_dependencies)
        names.update(self.optional_dependencies)
        return tuple(sorted(names))

    def version_for(self, package_name: str) -> str | None:
        for group in (
            self.dependencies,
            self.dev_dependencies,
            self.peer_dependencies,
            self.optional_dependencies,
        ):
            if package_name in group:
                return group[package_name]
        return None


@dataclass(frozen=True)
class PackageJsonScripts:
    values: dict[str, str]

    def items(self) -> tuple[tuple[str, str], ...]:
        return tuple((name, self.values[name]) for name in sorted(self.values))

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def has(self, name: str) -> bool:
        return name in self.values


@dataclass(frozen=True)
class PackageJsonManifest:
    path: Path
    raw: dict
    name: str | None
    version: str | None
    scripts: PackageJsonScripts
    dependencies: PackageJsonDependencySet
    main: str | None
    module: str | None
    types: str | None
    exports: object
    bin: object
    package_type: str | None
    private: bool
    workspaces: tuple[str, ...]


@dataclass(frozen=True)
class PackageJsonWorkspacePackage:
    repository_root: Path
    package_dir: Path
    manifest: PackageJsonManifest

    @property
    def repository_rel_path(self) -> str:
        return self.package_dir.relative_to(self.repository_root).as_posix()

    @property
    def package_json_rel_path(self) -> str:
        return self.manifest.path.relative_to(self.repository_root).as_posix()


@dataclass(frozen=True)
class PackageJsonWorkspace:
    repository_root: Path
    root_manifest: PackageJsonManifest
    packages: tuple[PackageJsonWorkspacePackage, ...]

    def package_names(self) -> tuple[str, ...]:
        names = []
        for package in self.packages:
            if package.manifest.name is None:
                raise ValueError(f"workspace package is missing a name: {package.manifest.path}")
            names.append(package.manifest.name)
        return tuple(names)

    def package_by_name(self, package_name: str) -> PackageJsonWorkspacePackage:
        for package in self.packages:
            if package.manifest.name == package_name:
                return package
        raise ValueError(f"unknown workspace package: {package_name}")
