from __future__ import annotations

from pathlib import Path
from typing import Callable

from suitcode.core.models import TestFramework
from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.npm.jest_runner import JestRunner
from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage
from suitcode.providers.npm.models import NpmTestAnalysis
from suitcode.providers.npm.test_tool_resolution import NpmTestToolResolver


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

    def __init__(
        self,
        tool_resolver_factory: Callable[[Path], NpmTestToolResolver] | None = None,
        jest_runner_factory: Callable[[Path, Path], JestRunner] | None = None,
    ) -> None:
        self._tool_resolver_factory = tool_resolver_factory or (lambda repository_root: NpmTestToolResolver(repository_root))
        self._jest_runner_factory = jest_runner_factory or (lambda repository_root, executable: JestRunner(repository_root, executable))

    def discover(self, package: PackageJsonWorkspacePackage) -> NpmTestAnalysis | None:
        package_name = package.manifest.name
        if package_name is None:
            raise ValueError(f"workspace package missing name: {package.manifest.path}")
        test_command = package.manifest.scripts.get("test")
        if test_command is None:
            return None
        framework = self._infer_framework(test_command)
        discovery_method = TestDiscoveryMethod.HEURISTIC_MANIFEST_GLOB
        discovery_tool: str | None = None
        if self._is_jest_command(test_command):
            try:
                executable = self._tool_resolver_factory(package.repository_root).resolve_jest()
            except ValueError:
                test_files = self._discover_test_files(package)
            else:
                test_files = self._jest_runner_factory(package.repository_root, executable).list_test_files(package.repository_rel_path)
                discovery_method = TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS
                discovery_tool = "jest"
        else:
            test_files = self._discover_test_files(package)
        return NpmTestAnalysis(
            package_name=package_name,
            package_path=package.repository_rel_path,
            framework=framework,
            test_files=test_files,
            discovery_method=discovery_method,
            discovery_tool=discovery_tool,
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

    def _is_jest_command(self, command: str) -> bool:
        return "jest" in command.lower()
