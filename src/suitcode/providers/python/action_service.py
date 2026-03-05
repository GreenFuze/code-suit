from __future__ import annotations

from suitcode.core.models import TestFramework
from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.shared.actions import (
    ProviderActionKind,
    ProviderActionProvenanceKind,
    ProviderActionSpec,
    ProviderActionTargetKind,
)
from suitcode.providers.python.models import PythonPackageComponentAnalysis, PythonRunnerAnalysis
from suitcode.providers.python.test_models import PythonTestAnalysis


class PythonActionService:
    def discover(
        self,
        components: tuple[PythonPackageComponentAnalysis, ...],
        runners: tuple[PythonRunnerAnalysis, ...],
        tests: tuple[PythonTestAnalysis, ...],
        has_build_system: bool,
    ) -> tuple[ProviderActionSpec, ...]:
        component_id_by_name = {
            component.package_name: f"component:python:{component.package_name}"
            for component in components
        }
        component_owner_ids = tuple(sorted(component_id_by_name.values()))
        actions: list[ProviderActionSpec] = []

        for runner in runners:
            runner_id = f"runner:python:{runner.script_name}"
            owner_ids = self._owner_ids_for_runner(runner, components, component_id_by_name)
            actions.append(
                ProviderActionSpec(
                    action_id=f"action:python:runner:{runner.script_name}",
                    display_name=f"Run python entrypoint `{runner.script_name}`",
                    kind=ProviderActionKind.RUNNER,
                    target_id=runner_id,
                    target_kind=ProviderActionTargetKind.RUNNER,
                    owner_ids=owner_ids,
                    argv=runner.argv,
                    cwd=runner.cwd,
                    dry_run_supported=True,
                    provenance_kind=ProviderActionProvenanceKind.MANIFEST,
                    provenance_tool=None,
                    provenance_summary="derived from pyproject.toml entry-point script metadata",
                    provenance_paths=("pyproject.toml", *runner.referenced_files),
                )
            )

        for test in tests:
            owner_ids = self._owner_ids_for_test(test, components, component_id_by_name)
            actions.append(
                ProviderActionSpec(
                    action_id=f"action:python:test:{test.name}",
                    display_name=f"Run {test.name} tests",
                    kind=ProviderActionKind.TEST,
                    target_id=test.test_id,
                    target_kind=ProviderActionTargetKind.TEST_DEFINITION,
                    owner_ids=owner_ids,
                    argv=self._test_argv(test),
                    cwd=None,
                    dry_run_supported=True,
                    provenance_kind=self._test_provenance_kind(test),
                    provenance_tool=test.discovery_tool,
                    provenance_summary=self._test_provenance_summary(test),
                    provenance_paths=test.evidence_paths or ("pyproject.toml",),
                )
            )

        if has_build_system:
            owner_ids = component_owner_ids
            actions.append(
                ProviderActionSpec(
                    action_id="action:python:build:repository",
                    display_name="Build python project",
                    kind=ProviderActionKind.BUILD,
                    target_id="repository:python:root",
                    target_kind=ProviderActionTargetKind.REPOSITORY,
                    owner_ids=owner_ids,
                    argv=("python", "-m", "build"),
                    cwd=None,
                    dry_run_supported=True,
                    provenance_kind=ProviderActionProvenanceKind.MANIFEST,
                    provenance_tool=None,
                    provenance_summary="derived from pyproject.toml build-system metadata",
                    provenance_paths=("pyproject.toml",),
                )
            )
        return self._finalize(actions)

    @staticmethod
    def _test_argv(test: PythonTestAnalysis) -> tuple[str, ...]:
        if test.framework == TestFramework.UNITTEST:
            return ("python", "-m", "unittest", "discover")
        if test.test_files:
            return ("pytest", *test.test_files)
        return ("pytest",)

    @staticmethod
    def _test_provenance_kind(test: PythonTestAnalysis) -> ProviderActionProvenanceKind:
        if test.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT:
            return ProviderActionProvenanceKind.TEST_TOOL
        return ProviderActionProvenanceKind.HEURISTIC

    @staticmethod
    def _test_provenance_summary(test: PythonTestAnalysis) -> str:
        if test.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT:
            return "derived from authoritative pytest collection output"
        if test.discovery_method == TestDiscoveryMethod.HEURISTIC_UNITTEST:
            return "derived from unittest heuristics and deterministic unittest discovery command"
        return "derived from pytest configuration heuristics"

    @staticmethod
    def _finalize(actions: list[ProviderActionSpec]) -> tuple[ProviderActionSpec, ...]:
        by_id: dict[str, ProviderActionSpec] = {}
        for action in actions:
            if action.action_id in by_id:
                raise ValueError(f"duplicate python action id detected: `{action.action_id}`")
            by_id[action.action_id] = action
        return tuple(sorted(by_id.values(), key=lambda item: item.action_id))

    @classmethod
    def _owner_ids_for_runner(
        cls,
        runner: PythonRunnerAnalysis,
        components: tuple[PythonPackageComponentAnalysis, ...],
        component_id_by_name: dict[str, str],
    ) -> tuple[str, ...]:
        runner_id = f"runner:python:{runner.script_name}"
        component_ids = cls._component_ids_for_paths(runner.referenced_files, components, component_id_by_name)
        return cls._merge_owner_ids(runner_id, component_ids)

    @classmethod
    def _owner_ids_for_test(
        cls,
        test: PythonTestAnalysis,
        components: tuple[PythonPackageComponentAnalysis, ...],
        component_id_by_name: dict[str, str],
    ) -> tuple[str, ...]:
        component_ids = cls._component_ids_for_paths(test.test_files, components, component_id_by_name)
        if not component_ids:
            component_ids = tuple(sorted(component_id_by_name.values()))
        return cls._merge_owner_ids(test.test_id, component_ids)

    @staticmethod
    def _merge_owner_ids(primary_owner_id: str, component_ids: tuple[str, ...]) -> tuple[str, ...]:
        owner_ids: list[str] = [primary_owner_id]
        for component_id in component_ids:
            if component_id not in owner_ids:
                owner_ids.append(component_id)
        return tuple(owner_ids)

    @staticmethod
    def _component_ids_for_paths(
        repository_rel_paths: tuple[str, ...],
        components: tuple[PythonPackageComponentAnalysis, ...],
        component_id_by_name: dict[str, str],
    ) -> tuple[str, ...]:
        matched: set[str] = set()
        for path in repository_rel_paths:
            normalized_path = path.replace("\\", "/").strip().removeprefix("./")
            for component in components:
                roots = component.source_roots or (component.package_path,)
                for root in roots:
                    normalized_root = root.replace("\\", "/").strip().removeprefix("./").removesuffix("/")
                    if not normalized_root:
                        continue
                    if normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}/"):
                        matched.add(component_id_by_name[component.package_name])
                        break
        return tuple(sorted(matched))
