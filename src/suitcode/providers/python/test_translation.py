from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.core.provenance_builders import heuristic_provenance, test_tool_provenance
from suitcode.core.tests.models import DiscoveredTestDefinition, TestDiscoveryMethod
from suitcode.providers.python.test_models import PythonTestAnalysis


class PythonTestTranslator:
    def _test_provenance(self, item: PythonTestAnalysis):
        if item.discovery_method == TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT:
            return (
                test_tool_provenance(
                    source_tool="pytest",
                    evidence_summary="discovered from pytest --collect-only -q",
                    evidence_paths=item.evidence_paths,
                ),
            )
        if item.discovery_method == TestDiscoveryMethod.HEURISTIC_CONFIG_GLOB:
            return (
                heuristic_provenance(
                    evidence_summary="derived from pytest configuration and test file glob heuristics",
                    evidence_paths=item.evidence_paths,
                ),
            )
        return (
            heuristic_provenance(
                evidence_summary="derived from unittest-oriented heuristics and test file globs",
                evidence_paths=item.evidence_paths,
            ),
        )

    def to_test_definition(self, item: PythonTestAnalysis) -> TestDefinition:
        return TestDefinition(
            id=item.test_id,
            name=item.name,
            framework=item.framework,
            test_files=item.test_files,
            provenance=self._test_provenance(item),
        )

    def to_discovered_test_definition(self, item: PythonTestAnalysis) -> DiscoveredTestDefinition:
        return DiscoveredTestDefinition(
            test_definition=self.to_test_definition(item),
            provenance=self._test_provenance(item),
        )
