from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.python.pytest_runner import PytestRunner
from suitcode.providers.python.test_discovery import PythonTestDiscoverer
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


class _FakePytestRunner:
    def __init__(self, files: tuple[str, ...]) -> None:
        self._files = files

    def collect_test_files(self) -> tuple[str, ...]:
        return self._files


class _FailingToolResolver:
    def resolve_pytest(self) -> Path:
        raise ValueError("pytest missing")


class _StaticToolResolver:
    def __init__(self, executable: Path) -> None:
        self._executable = executable

    def resolve_pytest(self) -> Path:
        return self._executable


def test_test_discovery_uses_authoritative_pytest_when_available(python_repo_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_repo_root)
    discoverer = PythonTestDiscoverer(
        python_repo_root,
        manifest,
        tool_resolver=_StaticToolResolver(python_repo_root / '.venv' / 'bin' / 'pytest'),
        pytest_runner_factory=lambda executable: _FakePytestRunner(('tests/test_basic.py',)),
    )

    tests = discoverer.discover()
    pytest_test = next(item for item in tests if item.test_id == 'test:python:pytest:root')
    unittest_test = next(item for item in tests if item.test_id == 'test:python:unittest:root')

    assert pytest_test.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT
    assert pytest_test.discovery_tool == 'pytest'
    assert pytest_test.test_files == ('tests/test_basic.py',)
    assert unittest_test.discovery_method == TestDiscoveryMethod.HEURISTIC_UNITTEST
    assert unittest_test.discovery_tool is None


def test_test_discovery_falls_back_to_heuristic_pytest_when_tool_is_unavailable(python_repo_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_repo_root)
    discoverer = PythonTestDiscoverer(
        python_repo_root,
        manifest,
        tool_resolver=_FailingToolResolver(),
    )

    tests = discoverer.discover()
    pytest_test = next(item for item in tests if item.test_id == 'test:python:pytest:root')

    assert pytest_test.discovery_method == TestDiscoveryMethod.HEURISTIC_CONFIG_GLOB
    assert pytest_test.discovery_tool is None
    assert pytest_test.test_files == ('tests/test_basic.py',)


def test_pytest_runner_malformed_output_raises(tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    with pytest.raises(ValueError):
        with patch(
            'suitcode.providers.python.pytest_runner.subprocess.run',
            return_value=CompletedProcess(args=['pytest'], returncode=0, stdout='not-a-real-path.py\n', stderr=''),
        ):
            PytestRunner(repo_root, Path(__import__('sys').executable)).collect_test_files()
