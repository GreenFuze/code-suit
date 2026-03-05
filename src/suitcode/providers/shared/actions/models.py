from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderActionKind(StrEnum):
    RUNNER = "runner"
    TEST = "test"
    BUILD = "build"


class ProviderActionTargetKind(StrEnum):
    REPOSITORY = "repository"
    COMPONENT = "component"
    RUNNER = "runner"
    TEST_DEFINITION = "test_definition"


class ProviderActionProvenanceKind(StrEnum):
    MANIFEST = "manifest"
    TEST_TOOL = "test_tool"
    HEURISTIC = "heuristic"


@dataclass(frozen=True)
class ProviderActionSpec:
    action_id: str
    display_name: str
    kind: ProviderActionKind
    target_id: str
    target_kind: ProviderActionTargetKind
    owner_ids: tuple[str, ...]
    argv: tuple[str, ...]
    cwd: str | None
    dry_run_supported: bool
    provenance_kind: ProviderActionProvenanceKind
    provenance_tool: str | None
    provenance_summary: str
    provenance_paths: tuple[str, ...]
