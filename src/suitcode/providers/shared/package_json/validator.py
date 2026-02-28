from __future__ import annotations

from pathlib import Path


class PackageJsonManifestValidator:
    def validate_root(self, raw: object, path: Path) -> dict:
        if not isinstance(raw, dict):
            raise ValueError(f"expected JSON object in {path}")
        self._validate_optional_string(raw, path, "name")
        self._validate_optional_string(raw, path, "version")
        self._validate_optional_string(raw, path, "main")
        self._validate_optional_string(raw, path, "module")
        self._validate_optional_string(raw, path, "types")
        self._validate_optional_string(raw, path, "type")
        self._validate_scripts(raw, path)
        self._validate_dependency_section(raw, path, "dependencies")
        self._validate_dependency_section(raw, path, "devDependencies")
        self._validate_dependency_section(raw, path, "peerDependencies")
        self._validate_dependency_section(raw, path, "optionalDependencies")
        self._validate_workspaces(raw, path)
        self._validate_bin(raw, path)
        return raw

    def _validate_optional_string(self, raw: dict, path: Path, field_name: str) -> None:
        value = raw.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"expected '{field_name}' to be a string in {path}")

    def _validate_scripts(self, raw: dict, path: Path) -> None:
        scripts = raw.get("scripts", {})
        if scripts is None:
            return
        if not isinstance(scripts, dict):
            raise ValueError(f"expected 'scripts' to be an object in {path}")
        for name, command in scripts.items():
            if not isinstance(name, str) or not isinstance(command, str):
                raise ValueError(f"invalid script entry in {path}")

    def _validate_dependency_section(self, raw: dict, path: Path, field_name: str) -> None:
        value = raw.get(field_name, {})
        if value is None:
            return
        if not isinstance(value, dict):
            raise ValueError(f"expected '{field_name}' to be an object in {path}")
        for name, version in value.items():
            if not isinstance(name, str) or not isinstance(version, str):
                raise ValueError(f"invalid dependency entry in '{field_name}' of {path}")

    def _validate_workspaces(self, raw: dict, path: Path) -> None:
        workspaces = raw.get("workspaces")
        if workspaces is None:
            return
        if not isinstance(workspaces, list):
            raise ValueError(f"expected 'workspaces' to be an array in {path}")
        for item in workspaces:
            if not isinstance(item, str):
                raise ValueError(f"expected every 'workspaces' entry to be a string in {path}")

    def _validate_bin(self, raw: dict, path: Path) -> None:
        bin_value = raw.get("bin")
        if bin_value is None:
            return
        if isinstance(bin_value, str):
            return
        if not isinstance(bin_value, dict):
            raise ValueError(f"expected 'bin' to be a string or object in {path}")
        for name, value in bin_value.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise ValueError(f"invalid 'bin' entry in {path}")
