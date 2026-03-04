from __future__ import annotations

from suitcode.core.models import TestDefinition
from suitcode.providers.python.test_models import PythonTestAnalysis


class PythonTestTranslator:
    def to_test_definition(self, item: PythonTestAnalysis) -> TestDefinition:
        return TestDefinition(
            id=item.test_id,
            name=item.name,
            framework=item.framework,
            test_files=item.test_files,
        )
