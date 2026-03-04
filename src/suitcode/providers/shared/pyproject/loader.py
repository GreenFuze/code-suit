from __future__ import annotations

import tomllib
from pathlib import Path

from suitcode.providers.shared.pyproject.models import (
    PyProjectBuildSystem,
    PyProjectManifest,
    PyProjectProject,
)
from suitcode.providers.shared.pyproject.validator import PyProjectValidator


class PyProjectLoader:
    def __init__(self, validator: PyProjectValidator | None = None) -> None:
        self._validator = validator or PyProjectValidator()

    def load(self, path: Path) -> PyProjectManifest:
        manifest_path = path.expanduser().resolve()
        if not manifest_path.exists():
            raise ValueError(f"pyproject.toml not found: {manifest_path}")
        try:
            raw = tomllib.loads(manifest_path.read_text(encoding='utf-8'))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid TOML in {manifest_path}: {exc}") from exc

        manifest = self._validator.validate_root(raw, manifest_path)
        build_system = manifest.get('build-system')
        project = manifest.get('project')
        tool = manifest.get('tool')

        return PyProjectManifest(
            path=manifest_path,
            raw=manifest,
            build_system=(
                None
                if build_system is None
                else PyProjectBuildSystem(
                    requires=tuple(build_system.get('requires', []) or ()),
                    build_backend=build_system.get('build-backend'),
                )
            ),
            project=(
                None
                if project is None
                else PyProjectProject(
                    name=project.get('name'),
                    version=project.get('version'),
                    dependencies=tuple(project.get('dependencies', []) or ()),
                    optional_dependencies={
                        group_name: tuple(group_values)
                        for group_name, group_values in dict(project.get('optional-dependencies', {}) or {}).items()
                    },
                    scripts=dict(project.get('scripts', {}) or {}),
                    gui_scripts=dict(project.get('gui-scripts', {}) or {}),
                    requires_python=project.get('requires-python'),
                )
            ),
            tool=dict(tool) if isinstance(tool, dict) else {},
        )
