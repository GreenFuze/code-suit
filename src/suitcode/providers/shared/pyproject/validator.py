from __future__ import annotations

from pathlib import Path


class PyProjectValidator:
    def validate_root(self, raw: object, manifest_path: Path) -> dict:
        if not isinstance(raw, dict):
            raise ValueError(f"pyproject.toml root must be a table: {manifest_path}")

        manifest = dict(raw)
        if 'build-system' in manifest:
            self._validate_build_system(manifest['build-system'], manifest_path)
        if 'project' in manifest:
            self._validate_project(manifest['project'], manifest_path)
        tool = manifest.get('tool')
        if tool is not None and not isinstance(tool, dict):
            raise ValueError(f"[tool] must be a table in {manifest_path}")
        return manifest

    def _validate_build_system(self, build_system: object, manifest_path: Path) -> None:
        if not isinstance(build_system, dict):
            raise ValueError(f"[build-system] must be a table in {manifest_path}")
        requires = build_system.get('requires')
        if requires is not None and not self._is_str_list(requires):
            raise ValueError(f"[build-system].requires must be an array of strings in {manifest_path}")
        build_backend = build_system.get('build-backend')
        if build_backend is not None and not isinstance(build_backend, str):
            raise ValueError(f"[build-system].build-backend must be a string in {manifest_path}")

    def _validate_project(self, project: object, manifest_path: Path) -> None:
        if not isinstance(project, dict):
            raise ValueError(f"[project] must be a table in {manifest_path}")

        for field_name in ('name', 'version', 'requires-python'):
            value = project.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"[project].{field_name} must be a string in {manifest_path}")

        dependencies = project.get('dependencies')
        if dependencies is not None and not self._is_str_list(dependencies):
            raise ValueError(f"[project].dependencies must be an array of strings in {manifest_path}")

        optional_dependencies = project.get('optional-dependencies')
        if optional_dependencies is not None:
            if not isinstance(optional_dependencies, dict):
                raise ValueError(f"[project].optional-dependencies must be a table in {manifest_path}")
            for group_name, group_values in optional_dependencies.items():
                if not isinstance(group_name, str) or not self._is_str_list(group_values):
                    raise ValueError(
                        f"[project].optional-dependencies entries must be arrays of strings in {manifest_path}"
                    )

        for field_name in ('scripts', 'gui-scripts'):
            values = project.get(field_name)
            if values is not None and not self._is_str_map(values):
                raise ValueError(f"[project].{field_name} must be a table of strings in {manifest_path}")

    @staticmethod
    def _is_str_list(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    @staticmethod
    def _is_str_map(value: object) -> bool:
        return isinstance(value, dict) and all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        )
