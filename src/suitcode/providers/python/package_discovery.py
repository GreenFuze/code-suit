from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from suitcode.core.models import ComponentKind
from suitcode.providers.python.models import PythonPackageComponentAnalysis
from suitcode.providers.shared.pyproject.models import PyProjectManifest


@dataclass(frozen=True)
class PythonPackagingLayout:
    source_roots: tuple[str, ...]
    top_level_packages: tuple[str, ...]
    backend_name: str | None


class PythonPackageDiscoverer:
    def discover(
        self,
        repository_root: Path,
        manifest: PyProjectManifest,
    ) -> tuple[PythonPackageComponentAnalysis, ...]:
        root = repository_root.expanduser().resolve()
        layout = self.resolve_layout(root, manifest)
        package_names = self._discover_top_level_packages(root, layout)
        components: list[PythonPackageComponentAnalysis] = []
        for package_name in package_names:
            package_path = self._resolve_package_path(root, layout, package_name)
            if package_path is None:
                continue
            components.append(
                PythonPackageComponentAnalysis(
                    package_name=package_name,
                    package_path=package_path,
                    component_kind=ComponentKind.PACKAGE,
                    source_roots=(package_path,),
                    artifact_paths=tuple(),
                )
            )
        return tuple(sorted(components, key=lambda item: item.package_name))

    def resolve_layout(self, repository_root: Path, manifest: PyProjectManifest) -> PythonPackagingLayout:
        tool = manifest.tool
        source_roots: list[str] = []
        top_level_packages: list[str] = []
        backend_name = self._backend_name(manifest)

        setuptools = tool.get("setuptools") if isinstance(tool.get("setuptools"), dict) else None
        if setuptools is not None:
            source_roots.extend(self._setuptools_source_roots(setuptools))
            top_level_packages.extend(self._setuptools_packages(setuptools))

        poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else None
        if poetry is not None:
            source_roots.extend(self._poetry_source_roots(poetry))
            top_level_packages.extend(self._poetry_packages(poetry))

        hatch = tool.get("hatch") if isinstance(tool.get("hatch"), dict) else None
        if hatch is not None:
            source_roots.extend(self._hatch_source_roots(hatch))
            top_level_packages.extend(self._hatch_packages(hatch))

        pdm = tool.get("pdm") if isinstance(tool.get("pdm"), dict) else None
        if pdm is not None:
            source_roots.extend(self._pdm_source_roots(pdm))
            top_level_packages.extend(self._pdm_packages(pdm))

        flit = tool.get("flit") if isinstance(tool.get("flit"), dict) else None
        if flit is not None:
            source_roots.extend(self._flit_source_roots(repository_root, flit))
            top_level_packages.extend(self._flit_packages(flit))

        if not source_roots:
            source_roots.append("src" if (repository_root / "src").is_dir() else ".")

        normalized_roots = tuple(dict.fromkeys(self._normalize_source_root(item) for item in source_roots))
        normalized_packages = tuple(
            dict.fromkeys(self._normalize_package_name(item) for item in top_level_packages if item)
        )
        return PythonPackagingLayout(
            source_roots=normalized_roots,
            top_level_packages=normalized_packages,
            backend_name=backend_name,
        )

    def _backend_name(self, manifest: PyProjectManifest) -> str | None:
        if manifest.build_system is None or manifest.build_system.build_backend is None:
            return None
        return manifest.build_system.build_backend.split(".", 1)[0]

    def _discover_top_level_packages(
        self,
        repository_root: Path,
        layout: PythonPackagingLayout,
    ) -> tuple[str, ...]:
        discovered: set[str] = set(layout.top_level_packages)
        for source_root in layout.source_roots:
            root = repository_root if source_root == "." else repository_root / source_root
            if not root.exists() or not root.is_dir():
                continue
            for child in sorted(root.iterdir(), key=lambda item: item.name):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if (child / "__init__.py").exists():
                    discovered.add(child.name)
        return tuple(sorted(discovered))

    def _resolve_package_path(
        self,
        repository_root: Path,
        layout: PythonPackagingLayout,
        package_name: str,
    ) -> str | None:
        package_rel = package_name.replace(".", "/")
        for source_root in layout.source_roots:
            root = repository_root if source_root == "." else repository_root / source_root
            candidate = root / package_rel / "__init__.py"
            if candidate.exists():
                return candidate.parent.relative_to(repository_root).as_posix()
        return None

    def _normalize_source_root(self, value: str) -> str:
        path = value.replace("\\", "/").strip("/")
        return path or "."

    def _normalize_package_name(self, value: str) -> str:
        candidate = value.replace("\\", "/").strip("/").replace("/", ".")
        return candidate.split(".", 1)[0]

    def _setuptools_source_roots(self, setuptools: dict) -> tuple[str, ...]:
        roots: list[str] = []
        package_dir = setuptools.get("package-dir")
        if isinstance(package_dir, dict):
            root = package_dir.get("")
            if isinstance(root, str):
                roots.append(root)
        packages = setuptools.get("packages")
        if isinstance(packages, dict):
            find = packages.get("find")
            if isinstance(find, dict):
                where = find.get("where")
                if isinstance(where, list):
                    roots.extend(item for item in where if isinstance(item, str))
        return tuple(roots)

    def _setuptools_packages(self, setuptools: dict) -> tuple[str, ...]:
        packages = setuptools.get("packages")
        if isinstance(packages, list):
            return tuple(self._normalize_package_name(item) for item in packages if isinstance(item, str))
        return tuple()

    def _poetry_source_roots(self, poetry: dict) -> tuple[str, ...]:
        packages = poetry.get("packages")
        roots: list[str] = []
        if isinstance(packages, list):
            for item in packages:
                if isinstance(item, dict):
                    root = item.get("from")
                    if isinstance(root, str):
                        roots.append(root)
        return tuple(roots)

    def _poetry_packages(self, poetry: dict) -> tuple[str, ...]:
        packages = poetry.get("packages")
        names: list[str] = []
        if isinstance(packages, list):
            for item in packages:
                if isinstance(item, dict):
                    include = item.get("include")
                    if isinstance(include, str):
                        names.append(include)
        name = poetry.get("name")
        if isinstance(name, str):
            names.append(name.replace("-", "_"))
        return tuple(self._normalize_package_name(item) for item in names if item)

    def _hatch_source_roots(self, hatch: dict) -> tuple[str, ...]:
        build = hatch.get("build") if isinstance(hatch.get("build"), dict) else {}
        targets = build.get("targets") if isinstance(build.get("targets"), dict) else {}
        wheel = targets.get("wheel") if isinstance(targets.get("wheel"), dict) else {}
        packages = wheel.get("packages")
        roots: list[str] = []
        if isinstance(packages, list):
            for item in packages:
                if isinstance(item, str):
                    roots.append(str(Path(item).parent).replace("\\", "/"))
        return tuple(roots)

    def _hatch_packages(self, hatch: dict) -> tuple[str, ...]:
        build = hatch.get("build") if isinstance(hatch.get("build"), dict) else {}
        targets = build.get("targets") if isinstance(build.get("targets"), dict) else {}
        wheel = targets.get("wheel") if isinstance(targets.get("wheel"), dict) else {}
        packages = wheel.get("packages")
        names: list[str] = []
        if isinstance(packages, list):
            for item in packages:
                if isinstance(item, str):
                    names.append(Path(item).name)
        return tuple(self._normalize_package_name(item) for item in names if item)

    def _pdm_source_roots(self, pdm: dict) -> tuple[str, ...]:
        build = pdm.get("build") if isinstance(pdm.get("build"), dict) else {}
        package_dir = build.get("package-dir")
        if isinstance(package_dir, str):
            return (package_dir,)
        return tuple()

    def _pdm_packages(self, pdm: dict) -> tuple[str, ...]:
        build = pdm.get("build") if isinstance(pdm.get("build"), dict) else {}
        includes = build.get("includes")
        names: list[str] = []
        if isinstance(includes, list):
            for item in includes:
                if isinstance(item, str):
                    names.append(Path(item).parts[0])
        return tuple(self._normalize_package_name(item) for item in names if item)

    def _flit_source_roots(self, repository_root: Path, flit: dict) -> tuple[str, ...]:
        return ("src",) if (repository_root / "src").is_dir() else (".",)

    def _flit_packages(self, flit: dict) -> tuple[str, ...]:
        module = flit.get("module") if isinstance(flit.get("module"), dict) else {}
        name = module.get("name")
        if isinstance(name, str):
            return (self._normalize_package_name(name),)
        metadata = flit.get("metadata") if isinstance(flit.get("metadata"), dict) else {}
        dist_name = metadata.get("module")
        if isinstance(dist_name, str):
            return (self._normalize_package_name(dist_name),)
        return tuple()
