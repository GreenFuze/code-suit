from __future__ import annotations

import pytest

from suitcode.core.change_evidence import ChangeEvidenceAssembler
from suitcode.core.change_models import ChangeEvidenceEdge, ChangeEvidencePreview, QualityGateInfo, RunnerImpact, TestImpact as ChangeTestImpact
from suitcode.core.code.models import CodeLocation
from suitcode.core.intelligence_models import ComponentDependencyEdge
from suitcode.core.models import Component, Runner, TestDefinition as CoreTestDefinition
from suitcode.core.provenance import SourceKind
from suitcode.core.provenance_builders import derived_summary_provenance, lsp_location_provenance, manifest_provenance, ownership_provenance
from suitcode.core.repository_models import OwnedNodeInfo
from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, ResolvedRelatedTest


def _component(component_id: str) -> Component:
    return Component(
        id=component_id,
        name=component_id.rsplit(":", 1)[-1],
        component_kind="library",
        language="typescript",
        source_roots=("packages/core/src",),
        provenance=(
            manifest_provenance(
                evidence_summary="component from package manifest",
                evidence_paths=("packages/core/package.json",),
            ),
        ),
    )


def _location(path: str, line: int, column: int) -> CodeLocation:
    return CodeLocation(
        repository_rel_path=path,
        line_start=line,
        line_end=line,
        column_start=column,
        column_end=column,
        provenance=(
            lsp_location_provenance(
                source_tool="typescript-language-server",
                repository_rel_path=path,
                operation="references",
            ),
        ),
    )


def _related_test(test_id: str) -> ResolvedRelatedTest:
    definition = CoreTestDefinition(
        id=test_id,
        name=test_id.rsplit(":", 1)[-1],
        framework="other",
        test_files=("packages/core/src/index.test.ts",),
        provenance=(
            derived_summary_provenance(
                source_kind=SourceKind.TEST_TOOL,
                source_tool="jest",
                evidence_summary="discovered from jest",
                evidence_paths=("packages/core/src/index.test.ts",),
            ),
        ),
    )
    return ResolvedRelatedTest(
        match=RelatedTestMatch(
            test_definition=definition,
            relation_reason="same_component",
            matched_repository_rel_path="packages/core/src/index.ts",
        ),
        discovered_test=DiscoveredTestDefinition(
            test_definition=definition,
            provenance=definition.provenance,
        ),
    )


def test_change_evidence_preview_rejects_inconsistent_counts() -> None:
    edge = ChangeEvidenceEdge(
        source_node_kind="change_target",
        source_node_id="change_target:file:packages/core/src/index.ts",
        target_node_kind="owner",
        target_node_id="component:npm:@monorepo/core",
        edge_kind="target_owner",
        reason="owner resolved from file ownership",
        provenance=(
            ownership_provenance(
                evidence_summary="owner resolved from ownership metadata",
                evidence_paths=("packages/core/src/index.ts",),
            ),
        ),
    )

    with pytest.raises(ValueError, match="sum\\(counts_by_kind.values\\(\\)\\) must equal total_edges"):
        ChangeEvidencePreview(
            total_edges=2,
            counts_by_kind={"target_owner": 1},
            edges_preview=(edge,),
            truncated=True,
        )


def test_change_evidence_assembler_sorts_and_truncates_preview() -> None:
    assembler = ChangeEvidenceAssembler()
    owner = OwnedNodeInfo(id="component:npm:@monorepo/core", kind="component", name="core")
    primary_component = _component("component:npm:@monorepo/core")
    dependent_components = tuple(
        _component(f"component:npm:@monorepo/dependent-{index:02d}") for index in range(30)
    )
    dependent_edges = tuple(
        ComponentDependencyEdge(
            source_component_id=component.id,
            target_id=primary_component.id,
            target_kind="component",
            dependency_scope="runtime",
            provenance=(
                manifest_provenance(
                    evidence_summary="dependency edge from package.json",
                    evidence_paths=("package.json",),
                ),
            ),
        )
        for component in dependent_components
    )

    preview = assembler.assemble(
        target_kind="file",
        target_value="packages/core/src/index.ts",
        evidence_path="packages/core/src/index.ts",
        owner=owner,
        primary_component=primary_component,
        reference_locations=(_location("packages/core/src/index.ts", 1, 1),),
        dependent_components=dependent_components,
        dependent_edges=dependent_edges,
        related_tests=tuple(),
        related_runners=tuple(),
        quality_gates=tuple(),
    )

    assert preview.total_edges == 33
    assert preview.truncated is True
    assert len(preview.edges_preview) == 25
    assert preview.edges_preview[0].edge_kind.value == "target_owner"
    assert preview.counts_by_kind["component_dependent_component"] == 30


def test_change_evidence_assembler_fails_when_dependent_edge_provenance_is_missing() -> None:
    assembler = ChangeEvidenceAssembler()
    owner = OwnedNodeInfo(id="component:npm:@monorepo/core", kind="component", name="core")
    primary_component = _component("component:npm:@monorepo/core")
    dependent_component = _component("component:npm:@monorepo/utils")

    with pytest.raises(ValueError, match="missing matching dependency-edge provenance"):
        assembler.assemble(
            target_kind="file",
            target_value="packages/core/src/index.ts",
            evidence_path="packages/core/src/index.ts",
            owner=owner,
            primary_component=primary_component,
            reference_locations=tuple(),
            dependent_components=(dependent_component,),
            dependent_edges=tuple(),
            related_tests=tuple(),
            related_runners=tuple(),
            quality_gates=tuple(),
        )


def test_change_evidence_assembler_adds_test_runner_and_quality_edges() -> None:
    assembler = ChangeEvidenceAssembler()
    owner = OwnedNodeInfo(id="component:npm:@monorepo/core", kind="component", name="core")
    primary_component = _component("component:npm:@monorepo/core")
    related_test = _related_test("test:npm:@monorepo/core")
    runner = Runner(
        id="runner:npm:@monorepo/core:start",
        name="start",
        argv=("npm", "run", "start"),
        provenance=(
            manifest_provenance(
                evidence_summary="runner from package manifest",
                evidence_paths=("packages/core/package.json",),
            ),
        ),
    )

    preview = assembler.assemble(
        target_kind="file",
        target_value="packages/core/src/index.ts",
        evidence_path="packages/core/src/index.ts",
        owner=owner,
        primary_component=primary_component,
        reference_locations=tuple(),
        dependent_components=tuple(),
        dependent_edges=tuple(),
        related_tests=(
            ChangeTestImpact(
                related_test=related_test,
                reason="same_file_context",
                provenance=related_test.provenance,
            ),
        ),
        related_runners=(
            RunnerImpact(
                runner=runner,
                reason="same_component",
                provenance=runner.provenance,
            ),
        ),
        quality_gates=(
            QualityGateInfo(
                provider_id="npm",
                provider_roles=("quality",),
                applies=True,
                reason="quality provider applies to the target file",
                provenance=(
                    derived_summary_provenance(
                        source_kind=SourceKind.QUALITY_TOOL,
                        source_tool="npm",
                        evidence_summary="quality gate derived from provider support",
                        evidence_paths=("packages/core/src/index.ts",),
                    ),
                ),
            ),
        ),
    )

    assert preview.counts_by_kind["target_related_test"] == 1
    assert preview.counts_by_kind["target_related_runner"] == 1
    assert preview.counts_by_kind["target_quality_gate"] == 1
