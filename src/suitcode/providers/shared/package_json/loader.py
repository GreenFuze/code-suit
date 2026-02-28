from __future__ import annotations

import json
from pathlib import Path

from suitcode.providers.shared.package_json.models import (
    PackageJsonDependencySet,
    PackageJsonManifest,
    PackageJsonScripts,
)
from suitcode.providers.shared.package_json.validator import PackageJsonManifestValidator


class PackageJsonLoader:
    def __init__(self, validator: PackageJsonManifestValidator | None = None) -> None:
        self._validator = validator or PackageJsonManifestValidator()

    def load(self, path: Path) -> PackageJsonManifest:
        manifest_path = path.expanduser().resolve()
        if not manifest_path.exists():
            raise ValueError(f"package.json not found: {manifest_path}")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {manifest_path}: {exc}") from exc

        manifest = self._validator.validate_root(raw, manifest_path)
        return PackageJsonManifest(
            path=manifest_path,
            raw=manifest,
            name=manifest.get("name"),
            version=manifest.get("version"),
            scripts=PackageJsonScripts(dict(manifest.get("scripts", {}) or {})),
            dependencies=PackageJsonDependencySet(
                dependencies=dict(manifest.get("dependencies", {}) or {}),
                dev_dependencies=dict(manifest.get("devDependencies", {}) or {}),
                peer_dependencies=dict(manifest.get("peerDependencies", {}) or {}),
                optional_dependencies=dict(manifest.get("optionalDependencies", {}) or {}),
            ),
            main=manifest.get("main"),
            module=manifest.get("module"),
            types=manifest.get("types"),
            exports=manifest.get("exports"),
            bin=manifest.get("bin"),
            package_type=manifest.get("type"),
            private=bool(manifest.get("private", False)),
            workspaces=tuple(manifest.get("workspaces", []) or ()),
        )
