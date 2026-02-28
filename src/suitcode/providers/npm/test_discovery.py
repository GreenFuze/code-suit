from __future__ import annotations

from suitcode.core.models import TestFramework
from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage
from suitcode.providers.npm.models import NpmTestAnalysis


class NpmTestDiscoverer:
    _TEST_PATTERNS = (
        "*.test.ts",
        "*.test.tsx",
        "*.test.js",
        "*.spec.ts",
        "*.spec.tsx",
        "*.spec.js",
        "test_*.py",
        "*_test.py",
    )

    def discover(self, package: PackageJsonWorkspacePackage) -> NpmTestAnalysis | None:
        package_name = package.manifest.name
        if package_name is None:
            raise ValueError(f"workspace package missing name: {package.manifest.path}")
        test_command = package.manifest.scripts.get("test")
        if test_command is None:
            return None
        framework = self._infer_framework(test_command)
        test_files = self._discover_test_files(package)
        return NpmTestAnalysis(
            package_name=package_name,
            package_path=package.repository_rel_path,
            framework=framework,
            test_files=test_files,
        )

    def _infer_framework(self, command: str) -> TestFramework:
        lowered = command.lower()
        if "pytest" in lowered:
            return TestFramework.PYTEST
        return TestFramework.OTHER

    def _discover_test_files(self, package: PackageJsonWorkspacePackage) -> tuple[str, ...]:
        found = set()
        for pattern in self._TEST_PATTERNS:
            for path in package.package_dir.rglob(pattern):
                if path.is_file():
                    found.add(path.relative_to(package.repository_root).as_posix())
        return tuple(sorted(found))
