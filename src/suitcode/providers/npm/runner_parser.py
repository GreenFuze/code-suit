from __future__ import annotations

import re
import shlex

from suitcode.providers.shared.package_json.models import PackageJsonWorkspacePackage
from suitcode.providers.npm.models import NpmRunnerAnalysis


class NpmRunnerScriptInspector:
    _SEPARATOR_PATTERN = re.compile(r"\s*(?:&&|\|\||;)\s*")

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
        normalized_command = command.strip()
        if not normalized_command:
            return None
        referenced_files = self._referenced_files(package_dir, normalized_command)
        return NpmRunnerAnalysis(
            package_name=package_name,
            package_path=package_path,
            script_name=script_name,
            command=command,
            executable="npm",
            argv=("npm", "run", script_name),
            cwd=package_path or None,
            referenced_files=referenced_files,
        )

    def _tokenized_segments(self, command: str) -> tuple[list[str], ...]:
        segments: list[list[str]] = []
        for segment in self._SEPARATOR_PATTERN.split(command):
            tokens = self._tokenize(segment)
            if not tokens:
                continue
            segments.append(tokens)
        return tuple(segments)

    def _tokenize(self, command: str) -> list[str]:
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return command.strip().split()

    def _referenced_files(self, package_dir, command: str) -> tuple[str, ...]:
        found: list[str] = []
        seen: set[str] = set()
        for tokens in self._tokenized_segments(command):
            for arg in tokens[1:]:
                if arg.startswith("-"):
                    continue
                candidate = (package_dir / arg).resolve()
                if candidate.exists() and candidate.is_file():
                    resolved = str(candidate)
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)
        return tuple(found)
