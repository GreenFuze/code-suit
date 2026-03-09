from __future__ import annotations

from pathlib import Path

from suitcode.core.models import TestDefinition as DefinitionNode
from suitcode.core.models.graph_types import TestFramework as FrameworkEnum
from suitcode.core.provenance_builders import heuristic_provenance
from suitcode.core.tests.models import (
    DiscoveredTestDefinition,
    RelatedTestTarget,
    TestExecutionResult as CoreTestExecutionResult,
    TestExecutionStatus as CoreTestExecutionStatus,
    TestTargetDescription as CoreTestTargetDescription,
)
from suitcode.core.tests.test_intelligence import TestIntelligence as RuntimeTestIntelligence
from suitcode.providers.provider_roles import ProviderRole
from suitcode.providers.runtime_capability_models import (
    RuntimeCapability,
    RuntimeCapabilityAvailability,
    TestRuntimeCapabilities as RuntimeTestCapabilities,
)
from suitcode.providers.test_provider_base import TestProviderBase
from suitcode.core.provenance import SourceKind


class _FakeRepository:
    def __init__(self, providers):
        self._providers = providers

    def get_providers_for_role(self, role: ProviderRole):
        if role == ProviderRole.TEST:
            return self._providers
        return tuple()


class _TestProvider(TestProviderBase):
    PROVIDER_ID = "fake-test"
    DISPLAY_NAME = "fake-test"
    BUILD_SYSTEMS = ("fake",)
    PROGRAMMING_LANGUAGES = ("other",)

    @classmethod
    def detect_roles(cls, repository_root: Path) -> frozenset[ProviderRole]:
        return frozenset({ProviderRole.TEST})

    def __init__(self, repository, suffix: str) -> None:
        super().__init__(repository)
        self._suffix = suffix
        self.discovered_calls = 0

    def get_tests(self):
        return (
            DefinitionNode(
                id=f"test:{self._suffix}",
                name=f"test-{self._suffix}",
                framework=FrameworkEnum.OTHER,
                provenance=(
                    heuristic_provenance(
                        evidence_summary="derived from fake manifest glob discovery",
                        evidence_paths=("tests/test_fake.py",),
                    ),
                ),
            ),
        )

    def get_discovered_tests(self):
        self.discovered_calls += 1
        return (
            DiscoveredTestDefinition(
                test_definition=self.get_tests()[0],
                provenance=(
                    heuristic_provenance(
                        evidence_summary="derived from fake manifest glob discovery",
                        evidence_paths=("tests/test_fake.py",),
                    ),
                ),
            ),
        )

    def get_related_tests(self, target: RelatedTestTarget):
        return tuple()

    def describe_test_target(self, test_id: str) -> CoreTestTargetDescription:
        if test_id != f"test:{self._suffix}":
            raise ValueError(f"unknown test id: `{test_id}`")
        return CoreTestTargetDescription(
            test_definition=self.get_tests()[0],
            command_argv=("pytest", "tests/test_fake.py"),
            command_cwd=None,
            is_authoritative=False,
            warning="heuristic target",
            provenance=(
                heuristic_provenance(
                    evidence_summary="derived from fake manifest glob discovery",
                    evidence_paths=("tests/test_fake.py",),
                ),
            ),
        )

    def run_test_targets(self, test_ids: tuple[str, ...], timeout_seconds: int) -> tuple[CoreTestExecutionResult, ...]:
        return tuple(
            CoreTestExecutionResult(
                test_id=test_id,
                status=CoreTestExecutionStatus.PASSED,
                success=True,
                command_argv=("pytest", "tests/test_fake.py"),
                command_cwd=None,
                exit_code=0,
                duration_ms=1,
                log_path=f".suit/runs/tests/{test_id}.log",
                output_excerpt="ok",
                provenance=(
                    heuristic_provenance(
                        evidence_summary="derived from fake manifest glob discovery",
                        evidence_paths=("tests/test_fake.py",),
                    ),
                ),
            )
            for test_id in test_ids
        )

    def get_test_runtime_capabilities(self) -> RuntimeTestCapabilities:
        discovery = RuntimeCapability(
            capability_id=f"fake.test.discovery.{self._suffix}",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.HEURISTIC,
            source_tool="fake-test",
            provenance=(
                heuristic_provenance(
                    evidence_summary="fake test discovery capability is available",
                    evidence_paths=("tests/test_fake.py",),
                ),
            ),
        )
        execution = RuntimeCapability(
            capability_id=f"fake.test.execution.{self._suffix}",
            availability=RuntimeCapabilityAvailability.AVAILABLE,
            source_kind=SourceKind.HEURISTIC,
            source_tool="fake-test",
            provenance=(
                heuristic_provenance(
                    evidence_summary="fake test execution capability is available",
                    evidence_paths=("tests/test_fake.py",),
                ),
            ),
        )
        return RuntimeTestCapabilities(discovery=discovery, execution=execution)


def test_test_intelligence_concatenates_and_sorts_definitions() -> None:
    repo = _FakeRepository(
        (
            _TestProvider(repository=None, suffix="b"),  # type: ignore[arg-type]
            _TestProvider(repository=None, suffix="a"),  # type: ignore[arg-type]
        )
    )
    intelligence = RuntimeTestIntelligence(repo)  # type: ignore[arg-type]

    assert tuple(node.id for node in intelligence.get_tests()) == ("test:a", "test:b")


def test_test_intelligence_describe_and_run_targets_route_by_test_id() -> None:
    repo = _FakeRepository(
        (
            _TestProvider(repository=None, suffix="b"),  # type: ignore[arg-type]
            _TestProvider(repository=None, suffix="a"),  # type: ignore[arg-type]
        )
    )
    intelligence = RuntimeTestIntelligence(repo)  # type: ignore[arg-type]

    description = intelligence.describe_test_target("test:a")
    results = intelligence.run_test_targets(("test:b", "test:a"), timeout_seconds=30)

    assert description.test_definition.id == "test:a"
    assert tuple(item.test_id for item in results) == ("test:b", "test:a")


def test_test_intelligence_caches_discovered_tests() -> None:
    provider = _TestProvider(repository=None, suffix="a")  # type: ignore[arg-type]
    repo = _FakeRepository((provider,))
    intelligence = RuntimeTestIntelligence(repo)  # type: ignore[arg-type]

    first = intelligence.get_discovered_tests()
    second = intelligence.get_discovered_tests()

    assert first == second
    assert provider.discovered_calls == 1
