from __future__ import annotations

import json
import subprocess
from pathlib import Path

from suitcode.core.models import ComponentKind, ProgrammingLanguage
from suitcode.providers.go.models import (
    GoExternalPackageAnalysis,
    GoModuleAnalysis,
    GoOwnedFileAnalysis,
    GoPackageAnalysis,
    GoPackageManagerAnalysis,
    GoWorkspaceAnalysis,
)


class GoWorkspaceAnalyzer:
    _IGNORE_DIRS = {'.git', '.suit', 'node_modules', 'vendor'}
    _VCS_HINTS = ('.git', '.hg', '.svn', '.bzr', '.suit')

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._analysis: GoWorkspaceAnalysis | None = None

    @classmethod
    def discover_module_roots(cls, repository_root: Path) -> tuple[Path, ...]:
        root = repository_root.expanduser().resolve()
        has_go_root = (root / 'go.mod').exists() or (root / 'go.work').exists()
        has_project_root_hint = (root / 'package.json').exists() or (root / 'pyproject.toml').exists()
        has_vcs_hint = any((root / marker).exists() for marker in cls._VCS_HINTS)
        if not has_go_root and not has_project_root_hint and not has_vcs_hint:
            return tuple()
        if cls._has_go_work(root):
            return tuple()
        go_mod_files = cls._go_mod_files(root)
        if not go_mod_files:
            return tuple()
        return tuple(item.parent for item in go_mod_files)

    @classmethod
    def detect_supported_workspace(cls, repository_root: Path) -> bool:
        return bool(cls.discover_module_roots(repository_root))

    @classmethod
    def detect_single_module(cls, repository_root: Path) -> bool:
        return len(cls.discover_module_roots(repository_root)) == 1

    @classmethod
    def _go_mod_files(cls, repository_root: Path) -> tuple[Path, ...]:
        paths: list[Path] = []
        for path in repository_root.rglob('go.mod'):
            relative_parts = {part.lower() for part in path.relative_to(repository_root).parts[:-1]}
            if relative_parts.intersection(cls._IGNORE_DIRS):
                continue
            paths.append(path.resolve())
        return tuple(sorted(paths))

    @classmethod
    def _has_go_work(cls, repository_root: Path) -> bool:
        for path in repository_root.rglob('go.work'):
            relative_parts = {part.lower() for part in path.relative_to(repository_root).parts[:-1]}
            if relative_parts.intersection(cls._IGNORE_DIRS):
                continue
            return True
        return False

    def analyze(self) -> GoWorkspaceAnalysis:
        if self._analysis is None:
            self._analysis = self._build_analysis()
        return self._analysis

    def _build_analysis(self) -> GoWorkspaceAnalysis:
        module_roots = self.discover_module_roots(self._repository_root)
        if not module_roots:
            raise ValueError(f'go provider requires one or more go.mod files and no go.work under `{self._repository_root}`')
        modules = tuple(self._analyze_module(module_root, module_roots) for module_root in module_roots)
        components = tuple(sorted((item for module in modules for item in module.components), key=lambda item: item.import_path))
        package_managers = tuple(sorted((module.package_manager for module in modules), key=lambda item: item.node_id))
        external_packages = tuple(
            sorted(
                {
                    (item.external_package_id, item.package_name, item.version_spec, item.manager_id): item
                    for module in modules
                    for item in module.external_packages
                }.values(),
                key=lambda item: item.external_package_id,
            )
        )
        files = tuple(
            sorted(
                {item.repository_rel_path: item for module in modules for item in module.files}.values(),
                key=lambda item: item.repository_rel_path,
            )
        )
        return GoWorkspaceAnalysis(
            module_roots_rel_path=tuple(module.module_root_rel_path for module in modules),
            modules=modules,
            components=components,
            package_managers=package_managers,
            external_packages=external_packages,
            files=files,
        )

    def _analyze_module(self, module_root: Path, all_module_roots: tuple[Path, ...]) -> GoModuleAnalysis:
        module_path = self._module_path(module_root)
        module_root_rel = self._module_root_rel_path(module_root)
        package_manager = GoPackageManagerAnalysis(
            node_id=self._package_manager_id(module_root_rel),
            module_root_rel_path=module_root_rel,
            display_name='go',
            manager='go',
            config_path=self._rel(module_root, 'go.mod'),
            owned_files=tuple(path for path in (self._rel(module_root, 'go.mod'), self._rel(module_root, 'go.sum')) if path is not None),
        )
        components = self._components(module_root, module_path, all_module_roots)
        external_packages = self._external_packages(module_root, package_manager.node_id)
        files = self._files(components, package_manager)
        return GoModuleAnalysis(
            module_root_rel_path=module_root_rel,
            module_path=module_path,
            components=components,
            package_manager=package_manager,
            external_packages=external_packages,
            files=files,
        )

    def _components(self, module_root: Path, module_path: str, all_module_roots: tuple[Path, ...]) -> tuple[GoPackageAnalysis, ...]:
        entries = self._run_go_json(module_root, ('go', 'list', '-buildvcs=false', '-json', './...'))
        components: list[GoPackageAnalysis] = []
        nested_module_roots = tuple(item for item in all_module_roots if item != module_root and self._is_under(item, module_root))
        for entry in entries:
            import_path = str(entry.get('ImportPath') or '').strip()
            dir_path = str(entry.get('Dir') or '').strip()
            package_name = str(entry.get('Name') or '').strip()
            if not import_path or not dir_path or not package_name:
                continue
            package_dir = Path(dir_path).resolve()
            try:
                directory_rel_path = package_dir.relative_to(self._repository_root).as_posix()
            except ValueError:
                continue
            if any(self._is_under(package_dir, nested_root) or package_dir == nested_root for nested_root in nested_module_roots):
                continue
            module_root_rel = self._module_root_rel_path(module_root)
            go_files = tuple(sorted(self._rel_from_repo(package_dir / name) for name in entry.get('GoFiles', []) if isinstance(name, str)))
            test_files = tuple(sorted(
                self._rel_from_repo(package_dir / name)
                for name in [*entry.get('TestGoFiles', []), *entry.get('XTestGoFiles', [])]
                if isinstance(name, str)
            ))
            imports = tuple(sorted(item for item in entry.get('Imports', []) if isinstance(item, str)))
            is_main = package_name == 'main'
            component_kind = ComponentKind.BINARY if is_main else ComponentKind.PACKAGE
            components.append(
                GoPackageAnalysis(
                    module_root_rel_path=module_root_rel,
                    import_path=import_path,
                    package_name=package_name,
                    directory_rel_path=directory_rel_path,
                    component_kind=component_kind,
                    source_roots=(directory_rel_path,),
                    artifact_paths=go_files,
                    go_files=go_files,
                    test_files=test_files,
                    imports=imports,
                    is_main=is_main,
                )
            )
        return tuple(sorted(components, key=lambda item: item.import_path))

    def _external_packages(self, module_root: Path, manager_id: str) -> tuple[GoExternalPackageAnalysis, ...]:
        try:
            modules = self._run_go_json(module_root, ('go', 'list', '-buildvcs=false', '-m', '-json', 'all'))
        except ValueError:
            return tuple()
        items: list[GoExternalPackageAnalysis] = []
        for entry in modules:
            path = entry.get('Path')
            version = entry.get('Version')
            if not isinstance(path, str) or not path.strip():
                continue
            if entry.get('Main') is True:
                continue
            items.append(
                GoExternalPackageAnalysis(
                    external_package_id=self._external_package_id(manager_id, path.strip()),
                    package_name=path.strip(),
                    version_spec=(version.strip() if isinstance(version, str) and version.strip() else '*'),
                    manager_id=manager_id,
                    evidence_paths=tuple(path for path in (self._rel(module_root, 'go.mod'), self._rel(module_root, 'go.sum')) if path is not None),
                )
            )
        return tuple(sorted(items, key=lambda item: item.package_name))

    def _files(
        self,
        components: tuple[GoPackageAnalysis, ...],
        package_manager: GoPackageManagerAnalysis,
    ) -> tuple[GoOwnedFileAnalysis, ...]:
        files: dict[str, GoOwnedFileAnalysis] = {}
        for analysis in components:
            owner_id = f'component:go:{analysis.import_path}'
            for rel_path in [*analysis.go_files, *analysis.test_files]:
                files[rel_path] = GoOwnedFileAnalysis(
                    repository_rel_path=rel_path,
                    owner_id=owner_id,
                    language=ProgrammingLanguage.GO,
                )
        for rel_path in package_manager.owned_files:
            files[rel_path] = GoOwnedFileAnalysis(
                repository_rel_path=rel_path,
                owner_id=package_manager.node_id,
                language=None,
            )
        return tuple(sorted(files.values(), key=lambda item: item.repository_rel_path))

    def _module_path(self, module_root: Path) -> str:
        payload = (module_root / 'go.mod').read_text(encoding='utf-8')
        for raw_line in payload.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith('module '):
                module_path = stripped[len('module ') :].strip()
                if module_path:
                    return module_path
        raise ValueError(f'go.mod in `{module_root}` does not declare a module path')

    def _run_go_json(self, module_root: Path, argv: tuple[str, ...]) -> tuple[dict[str, object], ...]:
        try:
            result = subprocess.run(
                argv,
                cwd=module_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError(f'failed to run `{" ".join(argv)}` in `{module_root}`') from exc
        return self._parse_json_stream(result.stdout)

    @staticmethod
    def _parse_json_stream(payload: str) -> tuple[dict[str, object], ...]:
        decoder = json.JSONDecoder()
        index = 0
        items: list[dict[str, object]] = []
        while index < len(payload):
            while index < len(payload) and payload[index].isspace():
                index += 1
            if index >= len(payload):
                break
            item, next_index = decoder.raw_decode(payload, index)
            if not isinstance(item, dict):
                raise ValueError('expected JSON object from go command output')
            items.append(item)
            index = next_index
        return tuple(items)

    def _rel(self, module_root: Path, filename: str) -> str | None:
        path = module_root / filename
        if not path.exists():
            return None
        return path.relative_to(self._repository_root).as_posix()

    def _rel_from_repo(self, path: Path) -> str:
        return path.resolve().relative_to(self._repository_root).as_posix()

    def _module_root_rel_path(self, module_root: Path) -> str:
        rel = module_root.relative_to(self._repository_root).as_posix()
        return '' if rel == '.' else rel

    @staticmethod
    def _is_under(path: Path, candidate_parent: Path) -> bool:
        try:
            path.relative_to(candidate_parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _package_manager_id(module_root_rel_path: str) -> str:
        return 'pkgmgr:go:root' if not module_root_rel_path else f'pkgmgr:go:{module_root_rel_path}'

    @staticmethod
    def _external_package_id(manager_id: str, package_name: str) -> str:
        normalized_manager = manager_id.replace(':', '/')
        return f'pkgext:go:{normalized_manager}:{package_name}'
