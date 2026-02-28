from __future__ import annotations

from pathlib import Path

from suitcode.core.models import ProgrammingLanguage
from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage


class NpmLanguageInferer:
    def infer(self, package: PackageJsonWorkspacePackage) -> ProgrammingLanguage:
        if self._is_typescript(package):
            return ProgrammingLanguage.TYPESCRIPT
        if self._has_extension(package.package_dir, (".py",)):
            return ProgrammingLanguage.PYTHON
        if (package.package_dir / "go.mod").exists() or self._has_extension(package.package_dir, (".go",)):
            return ProgrammingLanguage.GO
        if (package.package_dir / "Cargo.toml").exists() or self._has_extension(package.package_dir, (".rs",)):
            return ProgrammingLanguage.RUST
        if self._has_extension(package.package_dir, (".js", ".jsx", ".cjs", ".mjs")):
            return ProgrammingLanguage.JAVASCRIPT
        return ProgrammingLanguage.JAVASCRIPT

    def _is_typescript(self, package: PackageJsonWorkspacePackage) -> bool:
        manifest = package.manifest
        if (package.package_dir / "tsconfig.json").exists():
            return True
        for value in (manifest.types, manifest.main, manifest.module):
            if isinstance(value, str) and value.endswith((".ts", ".tsx", ".d.ts")):
                return True
        if self._exports_include_suffix(manifest.exports, (".ts", ".tsx", ".d.ts")):
            return True
        return self._has_extension(package.package_dir, (".ts", ".tsx", ".d.ts"))

    def _exports_include_suffix(self, exports: object, suffixes: tuple[str, ...]) -> bool:
        if isinstance(exports, str):
            return exports.endswith(suffixes)
        if isinstance(exports, dict):
            return any(self._exports_include_suffix(value, suffixes) for value in exports.values())
        if isinstance(exports, list):
            return any(self._exports_include_suffix(value, suffixes) for value in exports)
        return False

    def _has_extension(self, root: Path, suffixes: tuple[str, ...]) -> bool:
        return any(path.is_file() for suffix in suffixes for path in root.rglob(f"*{suffix}"))
