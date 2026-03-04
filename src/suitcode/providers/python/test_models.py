from __future__ import annotations

from dataclasses import dataclass

from suitcode.core.models import TestFramework


@dataclass(frozen=True)
class PythonTestAnalysis:
    test_id: str
    name: str
    framework: TestFramework
    test_files: tuple[str, ...]
