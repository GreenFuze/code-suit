from __future__ import annotations

from suitcode.providers.python.dependency_parser import PythonDependencyParser
from suitcode.providers.shared.pyproject import PyProjectWorkspaceLoader


def test_dependency_parser_extracts_names_and_specs(python_fixture_root) -> None:
    manifest = PyProjectWorkspaceLoader().load(python_fixture_root)
    parsed = PythonDependencyParser().parse(manifest, 'pkgmgr:python:root')

    assert {item.package_name for item in parsed} == {
        'fastapi',
        'mkdocs',
        'pydantic',
        'pytest',
        'ruff',
        'uvicorn',
    }
    assert {item.package_name: item.version_spec for item in parsed}['uvicorn'] == 'uvicorn[standard]>=0.30'
