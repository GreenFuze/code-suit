from __future__ import annotations

from packaging.requirements import Requirement

from suitcode.providers.python.models import PythonExternalPackageAnalysis
from suitcode.providers.shared.pyproject.models import PyProjectManifest


class PythonDependencyParser:
    def parse(
        self,
        manifest: PyProjectManifest,
        manager_id: str,
    ) -> tuple[PythonExternalPackageAnalysis, ...]:
        project = manifest.project
        if project is None:
            return tuple()

        dependencies: dict[str, str] = {}
        for requirement_string in project.dependencies:
            requirement = Requirement(requirement_string)
            dependencies.setdefault(requirement.name.lower(), requirement_string)

        for group_name in sorted(project.optional_dependencies):
            for requirement_string in project.optional_dependencies[group_name]:
                requirement = Requirement(requirement_string)
                dependencies.setdefault(requirement.name.lower(), requirement_string)

        return tuple(
            PythonExternalPackageAnalysis(
                package_name=package_name,
                version_spec=dependencies[package_name],
                manager_id=manager_id,
            )
            for package_name in sorted(dependencies)
        )
