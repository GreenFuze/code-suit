from __future__ import annotations

from suitcode.core.action_models import ActionKind, ActionTargetKind
from suitcode.core.provenance import SourceKind
from suitcode.providers.shared.actions import (
    ProviderActionKind,
    ProviderActionProvenanceKind,
    ProviderActionSpec,
    ProviderActionTargetKind,
    ProviderActionTranslator,
)


def test_provider_action_translation_maps_core_enums_and_provenance() -> None:
    translator = ProviderActionTranslator(provider_id="npm", default_test_tool="jest")
    action = translator.to_repository_action(
        ProviderActionSpec(
            action_id="action:npm:test:pkg",
            display_name="Run tests for pkg",
            kind=ProviderActionKind.TEST,
            target_id="test:npm:pkg",
            target_kind=ProviderActionTargetKind.TEST_DEFINITION,
            owner_ids=("component:npm:pkg", "test:npm:pkg"),
            argv=("npm", "run", "test", "--workspace", "pkg"),
            cwd=None,
            dry_run_supported=True,
            provenance_kind=ProviderActionProvenanceKind.TEST_TOOL,
            provenance_tool=None,
            provenance_summary="derived from authoritative jest test discovery and package test script",
            provenance_paths=("packages/pkg/package.json",),
        )
    )

    assert action.provider_id == "npm"
    assert action.kind == ActionKind.TEST_EXECUTION
    assert action.target_kind == ActionTargetKind.TEST_DEFINITION
    assert action.provenance[0].source_kind == SourceKind.TEST_TOOL
    assert action.provenance[0].source_tool == "jest"


def test_provider_action_translation_maps_manifest_provenance() -> None:
    translator = ProviderActionTranslator(provider_id="python", default_test_tool="pytest")
    action = translator.to_repository_action(
        ProviderActionSpec(
            action_id="action:python:build:repository",
            display_name="Build python project",
            kind=ProviderActionKind.BUILD,
            target_id="repository:python:root",
            target_kind=ProviderActionTargetKind.REPOSITORY,
            owner_ids=tuple(),
            argv=("python", "-m", "build"),
            cwd=None,
            dry_run_supported=True,
            provenance_kind=ProviderActionProvenanceKind.MANIFEST,
            provenance_tool=None,
            provenance_summary="derived from pyproject.toml build-system metadata",
            provenance_paths=("pyproject.toml",),
        )
    )

    assert action.kind == ActionKind.BUILD_EXECUTION
    assert action.target_kind == ActionTargetKind.REPOSITORY
    assert action.provenance[0].source_kind == SourceKind.MANIFEST
