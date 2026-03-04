from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.core.tests.models import DiscoveredTestDefinition, TestDiscoveryMethod
from suitcode.providers.python.test_models import PythonTestAnalysis


class PythonTestTranslator:
    def to_test_definition(self, item: PythonTestAnalysis) -> TestDefinition:
        return TestDefinition(
            id=item.test_id,
            name=item.name,
            framework=item.framework,
            test_files=item.test_files,
        )

    def to_discovered_test_definition(self, item: PythonTestAnalysis) -> DiscoveredTestDefinition:
        return DiscoveredTestDefinition(
            test_definition=self.to_test_definition(item),
            discovery_method=item.discovery_method,
            discovery_tool=item.discovery_tool,
            is_authoritative=item.discovery_method in {
                TestDiscoveryMethod.AUTHORITATIVE_JEST_LIST_TESTS,
                TestDiscoveryMethod.AUTHORITATIVE_PYTEST_COLLECT,
            },
        )
