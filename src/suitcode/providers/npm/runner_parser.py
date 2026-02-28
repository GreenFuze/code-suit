from __future__ import annotations

import re
import shlex

from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage
from suitcode.providers.npm.models import NpmRunnerAnalysis


class NpmRunnerScriptInspector:
    _SEPARATOR_PATTERN = re.compile(r"\s*(?:&&|\|\||;)\s*")
    _EXECUTABLES = {
        "python",
        "python3",
        "node",
        "docker",
        "go",
        "cargo",
        "bash",
        "sh",
        "pwsh",
        "powershell",
        "cmd",
    }

    def has_external_runner(self, package: PackageJsonWorkspacePackage) -> bool:
        return bool(self.inspect(package))

    def inspect(self, package: PackageJsonWorkspacePackage) -> tuple[NpmRunnerAnalysis, ...]:
        package_name = package.manifest.name
        if package_name is None:
            raise ValueError(f"workspace package missing name: {package.manifest.path}")

        analyses: list[NpmRunnerAnalysis] = []
        for script_name, command in package.manifest.scripts.items():
            analysis = self._inspect_command(package_name, package.repository_rel_path, package.package_dir, script_name, command)
            if analysis is not None:
                analyses.append(analysis)
        return tuple(analyses)

    def _inspect_command(
        self,
        package_name: str,
        package_path: str,
        package_dir,
        script_name: str,
        command: str,
    ) -> NpmRunnerAnalysis | None:
        for segment in self._SEPARATOR_PATTERN.split(command):
            tokens = self._tokenize(segment)
            if not tokens:
                continue
            executable = tokens[0]
            if not self._is_external_executable(executable):
                continue
            referenced_files = self._referenced_files(package_dir, tokens[1:])
            return NpmRunnerAnalysis(
                package_name=package_name,
                package_path=package_path,
                script_name=script_name,
                command=command,
                executable=executable,
                argv=tuple(tokens),
                cwd=package_path,
                referenced_files=referenced_files,
            )
        return None

    def _tokenize(self, command: str) -> list[str]:
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return command.strip().split()

    def _is_external_executable(self, executable: str) -> bool:
        return executable in self._EXECUTABLES or executable.startswith(("./", ".\\"))

    def _referenced_files(self, package_dir, args: list[str]) -> tuple[str, ...]:
        found = []
        for arg in args:
            if arg.startswith("-"):
                continue
            candidate = (package_dir / arg).resolve()
            if candidate.exists() and candidate.is_file():
                found.append(candidate)
        return tuple(str(path) for path in found)
