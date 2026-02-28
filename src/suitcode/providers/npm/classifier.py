from __future__ import annotations

from suitcode.core.models import ComponentKind
from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage
from suitcode.providers.npm.runner_parser import NpmRunnerScriptInspector


class NpmPackageClassifier:
    def __init__(self, runner_inspector: NpmRunnerScriptInspector | None = None) -> None:
        self._runner_inspector = runner_inspector or NpmRunnerScriptInspector()

    def classify(self, package: PackageJsonWorkspacePackage) -> str:
        root_segment = self._root_segment(package)
        if root_segment == "aggregators":
            return "aggregator"
        if root_segment == "tools":
            return "component"
        if root_segment in {"apps", "services", "packages", "libs", "modules"}:
            return "component"
        raise ValueError(f"unsupported npm workspace package location: {package.package_dir}")

    def component_kind_for(self, package: PackageJsonWorkspacePackage) -> ComponentKind:
        root_segment = self._root_segment(package)
        mapping = {
            "apps": ComponentKind.BINARY,
            "services": ComponentKind.SERVICE,
            "packages": ComponentKind.PACKAGE,
            "libs": ComponentKind.LIBRARY,
            "modules": ComponentKind.PACKAGE,
            "tools": ComponentKind.PACKAGE,
        }
        if root_segment not in mapping:
            raise ValueError(f"unsupported component location: {package.package_dir}")
        return mapping[root_segment]

    def _root_segment(self, package: PackageJsonWorkspacePackage) -> str:
        relative = package.repository_rel_path
        return relative.split("/", 1)[0]
