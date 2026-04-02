from __future__ import annotations

from types import SimpleNamespace

import pytest

from suitcode.core.code.models import CodeLocation
from suitcode.core.implementation_flow_service import ImplementationFlowService
from suitcode.core.intelligence_models import (
    ImplementationFlowStepKind,
    ImplementationFlowStepRef,
    RenderEdgeKind,
    RenderEdgeRef,
    StaticFlowEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.models.graph_types import TestFramework as GraphTestFramework
from suitcode.core.models.nodes import TestDefinition as GraphTestDefinition
from suitcode.core.provenance_builders import (
    dependency_graph_provenance,
    heuristic_provenance,
    lsp_provenance,
    test_tool_provenance as build_test_tool_provenance,
)
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, ResolvedRelatedTest


def test_implementation_flow_step_rejects_heuristic_provenance() -> None:
    with pytest.raises(ValueError, match="must not be heuristic"):
        ImplementationFlowStepRef(
            repository_rel_path="src/App.tsx",
            line_start=1,
            column_start=1,
            step_kind=ImplementationFlowStepKind.STATE_SITE,
            source_label="status",
            provenance=(
                heuristic_provenance(
                    evidence_summary="guessed state site",
                    evidence_paths=("src/App.tsx",),
                ),
            ),
        )


def test_implementation_flow_service_merges_generic_and_provider_steps() -> None:
    render_edge = RenderEdgeRef(
        repository_rel_path="src/Child.tsx",
        relationship_kind=RenderEdgeKind.RENDERS,
        line_start=14,
        column_start=5,
        prop_names=("status", "onReady"),
        has_spread_props=False,
        provenance=(
            dependency_graph_provenance(
                source_tool="typescript",
                evidence_summary="resolved JSX render edge",
                evidence_paths=("src/App.tsx", "src/Child.tsx"),
            ),
        ),
    )
    local_flow = StaticFlowEdgeRef(
        repository_rel_path="src/App.tsx",
        edge_kind=StaticFlowEdgeKind.PRODUCES_VALUE_FOR,
        line_start=9,
        column_start=7,
        source_label="loadState",
        target_label="status",
        provenance=(
            dependency_graph_provenance(
                source_tool="typescript",
                evidence_summary="resolved local flow edge",
                evidence_paths=("src/App.tsx",),
            ),
        ),
    )
    implementation_location = CodeLocation(
        repository_rel_path="src/integration.ts",
        line_start=3,
        column_start=1,
        provenance=(
            lsp_provenance(
                source_tool="typescript-language-server",
                evidence_summary="implementation location",
                evidence_paths=("src/integration.ts",),
            ),
        ),
    )
    test_definition = GraphTestDefinition(
        id="test:npm:frontend",
        name="frontend:test",
        framework=GraphTestFramework.OTHER,
        test_files=("src/App.test.tsx",),
        provenance=(
            build_test_tool_provenance(
                source_tool="jest",
                evidence_summary="jest discovered tests",
                evidence_paths=("src/App.test.tsx",),
            ),
        ),
    )
    related_test = ResolvedRelatedTest(
        match=RelatedTestMatch(
            test_definition=test_definition,
            relation_reason="same_package",
            matched_repository_rel_path="src/App.tsx",
        ),
        discovered_test=DiscoveredTestDefinition(
            test_definition=test_definition,
            provenance=test_definition.provenance,
        ),
    )
    provider_step = ImplementationFlowStepRef(
        repository_rel_path="src/App.tsx",
        line_start=6,
        column_start=9,
        step_kind=ImplementationFlowStepKind.STATE_SITE,
        source_label="status",
        target_label="setStatus",
        detail_label="useState",
        provenance=(
            dependency_graph_provenance(
                source_tool="typescript",
                evidence_summary="explicit React useState",
                evidence_paths=("src/App.tsx",),
            ),
        ),
    )

    class _StubCode:
        def get_file_render_edges(self, repository_rel_path: str, relationship_kind=None):
            if relationship_kind == RenderEdgeKind.RENDERS:
                return (render_edge,)
            return tuple()

        def get_file_local_flow_edges(self, repository_rel_path: str):
            return (local_flow,)

        def get_file_implementation_locations(self, repository_rel_path: str):
            return (implementation_location,)

        def get_file_implementation_flow_steps(self, repository_rel_path: str):
            return (provider_step,)

    class _StubTests:
        def get_related_tests(self, target):
            return (related_test,)

    class _StubRepository:
        def __init__(self) -> None:
            self.code = _StubCode()
            self.tests = _StubTests()

        def get_providers_for_file_role(self, repository_rel_path: str, role):
            return (SimpleNamespace(attachment=SimpleNamespace(provider_id="npm")),)

    summary = ImplementationFlowService(_StubRepository()).summarize_file(
        "src/App.tsx",
        detail_level="compact",
    )

    assert summary is not None
    assert summary.step_count == 5
    assert summary.provider_ids == ("npm",)
    assert [item.step_kind for item in summary.steps_preview] == [
        ImplementationFlowStepKind.STATE_SITE,
        ImplementationFlowStepKind.PROP_EDGE,
        ImplementationFlowStepKind.LOCAL_FLOW_EDGE,
        ImplementationFlowStepKind.IMPLEMENTATION_ANCHOR,
    ]
    assert summary.steps_preview[0].source_label == "status"
    assert summary.steps_preview[1].target_label == "Child.tsx"
    assert summary.steps_preview[2].target_label == "status"
