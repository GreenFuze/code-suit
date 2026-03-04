from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.models import TestFramework
from suitcode.core.tests.models import TestDiscoveryMethod


@dataclass(frozen=True)
class PythonTestAnalysis:
    test_id: str
    name: str
    framework: TestFramework
    test_files: tuple[str, ...]
    discovery_method: TestDiscoveryMethod
    discovery_tool: str | None
