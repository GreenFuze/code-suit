from __future__ import annotations

from suitcode.providers.python.test_discovery import PythonTestDiscoverer
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


def test_test_discovery_finds_real_pytest_and_unittest_targets(python_repo_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_repo_root)
    tests = PythonTestDiscoverer(python_repo_root, manifest).discover()

    assert tuple(item.test_id for item in tests) == ('test:python:pytest:root', 'test:python:unittest:root')
    assert tests[0].test_files == ('tests/test_basic.py',)
    assert tests[1].test_files == ('tests_unittest/test_unittest_sample.py',)
