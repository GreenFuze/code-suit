from __future__ import annotations

from suitcode.core.tests.models import TestDiscoveryMethod
from suitcode.providers.shared.actions import (
    ProviderActionKind,
    ProviderActionProvenanceKind,
    ProviderActionSpec,
    ProviderActionTargetKind,
)
from suitcode.providers.npm.models import NpmPackageAnalysis, NpmRunnerAnalysis, NpmTestAnalysis


class NpmActionService:
    def discover(
        self,
        components: tuple[NpmPackageAnalysis, ...],
        runners: tuple[NpmRunnerAnalysis, ...],
        tests: tuple[NpmTestAnalysis, ...],
    ) -> tuple[ProviderActionSpec, ...]:
        component_id_by_package = {
            component.package_name: f"component:npm:{component.package_name}"
            for component in components
        }
        runner_by_package_script = {
            (runner.package_name, runner.script_name): runner
            for runner in runners
        }
        actions: list[ProviderActionSpec] = []
        for runner in runners:
            runner_id = self._runner_id(runner)
            component_id = component_id_by_package.get(runner.package_name)
            owner_ids = (runner_id,) if component_id is None else (component_id, runner_id)
            evidence_paths = self._runner_evidence_paths(runner)
            actions.append(
                ProviderActionSpec(
                    action_id=f"action:npm:runner:{runner.package_name}:{runner.script_name}",
                    display_name=f"Run {runner.package_name}:{runner.script_name}",
                    kind=ProviderActionKind.RUNNER,
                    target_id=runner_id,
                    target_kind=ProviderActionTargetKind.RUNNER,
                    owner_ids=owner_ids,
                    argv=runner.argv,
                    cwd=runner.cwd,
                    dry_run_supported=True,
                    provenance_kind=ProviderActionProvenanceKind.MANIFEST,
                    provenance_tool=None,
                    provenance_summary="derived from npm package script metadata",
                    provenance_paths=evidence_paths,
                )
            )
            if runner.script_name == "build" and component_id is not None:
                actions.append(
                    ProviderActionSpec(
                        action_id=f"action:npm:build:{runner.package_name}",
                        display_name=f"Build {runner.package_name}",
                        kind=ProviderActionKind.BUILD,
                        target_id=component_id,
                        target_kind=ProviderActionTargetKind.COMPONENT,
                        owner_ids=(component_id, runner_id),
                        argv=runner.argv,
                        cwd=runner.cwd,
                        dry_run_supported=True,
                        provenance_kind=ProviderActionProvenanceKind.MANIFEST,
                        provenance_tool=None,
                        provenance_summary="derived from npm build script metadata",
                        provenance_paths=evidence_paths,
                    )
                )

        for test in tests:
            component_id = component_id_by_package.get(test.package_name)
            if component_id is None:
                continue
            test_runner = runner_by_package_script.get((test.package_name, "test"))
            test_id = f"test:npm:{test.package_name}"
            argv, cwd = self._test_invocation(test, test_runner)
            actions.append(
                ProviderActionSpec(
                    action_id=f"action:npm:test:{test.package_name}",
                    display_name=f"Run tests for {test.package_name}",
                    kind=ProviderActionKind.TEST,
                    target_id=test_id,
                    target_kind=ProviderActionTargetKind.TEST_DEFINITION,
                    owner_ids=(component_id, test_id),
                    argv=argv,
                    cwd=cwd,
                    dry_run_supported=True,
                    provenance_kind=self._test_provenance_kind(test),
                    provenance_tool=test.discovery_tool,
                    provenance_summary=self._test_provenance_summary(test),
                    provenance_paths=self._test_evidence_paths(test),
                )
            )
        return self._finalize(actions)

    @staticmethod
    def _runner_evidence_paths(runner: NpmRunnerAnalysis) -> tuple[str, ...]:
        return (f"{runner.package_path}/package.json",)

    @staticmethod
    def _runner_id(runner: NpmRunnerAnalysis) -> str:
        return f"runner:npm:{runner.package_name}:{runner.script_name}"

    @staticmethod
    def _test_evidence_paths(test: NpmTestAnalysis) -> tuple[str, ...]:
        if test.evidence_paths:
            return test.evidence_paths
        return (f"{test.package_path}/package.json",)

    @staticmethod
    def _test_provenance_kind(test: NpmTestAnalysis) -> ProviderActionProvenanceKind:
        if test.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS:
            return ProviderActionProvenanceKind.TEST_TOOL
        return ProviderActionProvenanceKind.HEURISTIC

    @staticmethod
    def _test_provenance_summary(test: NpmTestAnalysis) -> str:
        if test.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS:
            return "derived from authoritative jest test discovery and package test script"
        return "derived from heuristic npm test discovery and package test script"

    @staticmethod
    def _test_invocation(
        test: NpmTestAnalysis,
        runner: NpmRunnerAnalysis | None,
    ) -> tuple[tuple[str, ...], str | None]:
        if runner is not None:
            return runner.argv, runner.cwd
        return ("npm", "run", "test", "--workspace", test.package_name), None

    @staticmethod
    def _finalize(actions: list[ProviderActionSpec]) -> tuple[ProviderActionSpec, ...]:
        by_id: dict[str, ProviderActionSpec] = {}
        for action in actions:
            if action.action_id in by_id:
                raise ValueError(f"duplicate npm action id detected: `{action.action_id}`")
            by_id[action.action_id] = action
        return tuple(sorted(by_id.values(), key=lambda item: item.action_id))
