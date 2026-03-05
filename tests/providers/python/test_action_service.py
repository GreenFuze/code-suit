from __future__ import annotations

from suitcode.core.models import ComponentKind, TestFramework as CoreTestFramework
from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.python.action_service import PythonActionService
from suitcode.providers.python.models import PythonPackageComponentAnalysis, PythonRunnerAnalysis
from suitcode.providers.python.test_models import PythonTestAnalysis


def test_python_action_service_assigns_runner_owner_by_referenced_file() -> None:
    service = PythonActionService()
    components = (
        PythonPackageComponentAnalysis(
            package_name="alpha",
            package_path="src/alpha",
            component_kind=ComponentKind.LIBRARY,
            source_roots=("src/alpha",),
            artifact_paths=tuple(),
        ),
        PythonPackageComponentAnalysis(
            package_name="beta",
            package_path="src/beta",
            component_kind=ComponentKind.SERVICE,
            source_roots=("src/beta",),
            artifact_paths=tuple(),
        ),
    )
    runners = (
        PythonRunnerAnalysis(
            script_name="serve-beta",
            entrypoint="beta.app:main",
            argv=("python", "-m", "beta.app"),
            cwd=None,
            referenced_files=("src/beta/app.py",),
        ),
    )

    actions = service.discover(components=components, runners=runners, tests=tuple(), has_build_system=False)
    runner_action = next(item for item in actions if item.kind.value == "runner")

    assert runner_action.owner_ids[0] == "runner:python:serve-beta"
    assert "component:python:beta" in runner_action.owner_ids
    assert "component:python:alpha" not in runner_action.owner_ids


def test_python_action_service_assigns_test_to_all_components_when_unmapped() -> None:
    service = PythonActionService()
    components = (
        PythonPackageComponentAnalysis(
            package_name="alpha",
            package_path="src/alpha",
            component_kind=ComponentKind.LIBRARY,
            source_roots=("src/alpha",),
            artifact_paths=tuple(),
        ),
        PythonPackageComponentAnalysis(
            package_name="beta",
            package_path="src/beta",
            component_kind=ComponentKind.SERVICE,
            source_roots=("src/beta",),
            artifact_paths=tuple(),
        ),
    )
    tests = (
        PythonTestAnalysis(
            test_id="test:python:pytest:root",
            name="pytest",
            framework=CoreTestFramework.PYTEST,
            test_files=("tests/test_app.py",),
            discovery_method=TestDiscoveryMethod.HEURISTIC_CONFIG_GLOB,
            discovery_tool=None,
            evidence_paths=("pyproject.toml", "tests/test_app.py"),
        ),
    )

    actions = service.discover(components=components, runners=tuple(), tests=tests, has_build_system=False)
    test_action = next(item for item in actions if item.kind.value == "test")

    assert test_action.owner_ids[0] == "test:python:pytest:root"
    assert "component:python:alpha" in test_action.owner_ids
    assert "component:python:beta" in test_action.owner_ids
