from __future__ import annotations

import configparser
from pathlib import Path
from typing import Callable

from packaging.requirements import Requirement

from suitcode.core.models import TestFramework
from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.python.pytest_runner import PytestRunner
from suitcode.providers.python.test_models import PythonTestAnalysis
from suitcode.providers.python.python_tool_resolution import PythonToolResolver
from suitcode.providers.shared.pyproject.models import PyProjectManifest


class PythonTestDiscoverer:
    def __init__(
        self,
        repository_root: Path,
        manifest: PyProjectManifest,
        tool_resolver: PythonToolResolver | None = None,
        pytest_runner_factory: Callable[[Path], PytestRunner] | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._manifest = manifest
        self._tool_resolver = tool_resolver or PythonToolResolver(self._repository_root)
        self._pytest_runner_factory = pytest_runner_factory or (lambda executable: PytestRunner(self._repository_root, executable))

    def discover(self) -> tuple[PythonTestAnalysis, ...]:
        analyses: list[PythonTestAnalysis] = []
        pytest_analysis = self._discover_pytest()
        if pytest_analysis is not None:
            analyses.append(pytest_analysis)
        unittest_analysis = self._discover_unittest()
        if unittest_analysis is not None:
            analyses.append(unittest_analysis)
        return tuple(sorted(analyses, key=lambda item: item.test_id))

    def _discover_pytest(self) -> PythonTestAnalysis | None:
        if not self._has_pytest_signal():
            return None
        try:
            executable = self._tool_resolver.resolve_pytest()
        except ValueError:
            roots = self._pytest_roots()
            files = self._collect_test_files(roots, ('test_*.py', '*_test.py'))
            return PythonTestAnalysis(
                test_id='test:python:pytest:root',
                name='pytest',
                framework=TestFramework.PYTEST,
                test_files=files,
                discovery_method=TestDiscoveryMethod.HEURISTIC_CONFIG_GLOB,
                discovery_tool=None,
                evidence_paths=('pyproject.toml', *files),
            )
        files = self._pytest_runner_factory(executable).collect_test_files()
        return PythonTestAnalysis(
            test_id='test:python:pytest:root',
            name='pytest',
            framework=TestFramework.PYTEST,
            test_files=files,
            discovery_method=TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT,
            discovery_tool='pytest',
            evidence_paths=('pyproject.toml', *files),
        )

    def _discover_unittest(self) -> PythonTestAnalysis | None:
        root = self._unittest_root()
        if root is None:
            return None
        files = self._collect_test_files((root,), ('test*.py',))
        return PythonTestAnalysis(
            test_id='test:python:unittest:root',
            name='unittest',
            framework=TestFramework.UNITTEST,
            test_files=files,
            discovery_method=TestDiscoveryMethod.HEURISTIC_UNITTEST,
            discovery_tool=None,
            evidence_paths=('pyproject.toml', *files),
        )

    def _has_pytest_signal(self) -> bool:
        tool = self._manifest.tool.get('pytest')
        if isinstance(tool, dict) and tool.get('ini_options') is not None:
            return True
        if (self._repository_root / 'pytest.ini').exists():
            return True
        if (self._repository_root / 'setup.cfg').exists() and '[tool:pytest]' in (self._repository_root / 'setup.cfg').read_text(encoding='utf-8'):
            return True
        if (self._repository_root / 'tox.ini').exists() and 'pytest' in (self._repository_root / 'tox.ini').read_text(encoding='utf-8'):
            return True
        project = self._manifest.project
        if project is None:
            return False
        for requirement_string in project.dependencies:
            if Requirement(requirement_string).name.lower() == 'pytest':
                return True
        for group_values in project.optional_dependencies.values():
            for requirement_string in group_values:
                if Requirement(requirement_string).name.lower() == 'pytest':
                    return True
        return False

    def _pytest_roots(self) -> tuple[str, ...]:
        tool = self._manifest.tool.get('pytest')
        if isinstance(tool, dict):
            ini_options = tool.get('ini_options')
            if isinstance(ini_options, dict):
                testpaths = ini_options.get('testpaths')
                if isinstance(testpaths, list) and all(isinstance(item, str) for item in testpaths):
                    return tuple(testpaths)
        return ('tests',)

    def _unittest_root(self) -> str | None:
        tox_path = self._repository_root / 'tox.ini'
        if not tox_path.exists():
            return None
        parser = configparser.ConfigParser()
        parser.read(tox_path, encoding='utf-8')
        for section in parser.sections():
            if not section.startswith('testenv'):
                continue
            commands = parser.get(section, 'commands', fallback='')
            if 'unittest' not in commands:
                continue
            marker = 'discover'
            if marker in commands:
                after = commands.split(marker, 1)[1].strip().splitlines()[0].strip()
                if after:
                    return after.split()[0]
            return 'tests'
        return None

    def _collect_test_files(self, roots: tuple[str, ...], patterns: tuple[str, ...]) -> tuple[str, ...]:
        discovered: set[str] = set()
        for root_name in roots:
            root = (self._repository_root / root_name).resolve()
            if not root.exists() or not root.is_dir():
                continue
            for pattern in patterns:
                for file_path in root.rglob(pattern):
                    if file_path.is_file():
                        discovered.add(file_path.relative_to(self._repository_root).as_posix())
        return tuple(sorted(discovered))
