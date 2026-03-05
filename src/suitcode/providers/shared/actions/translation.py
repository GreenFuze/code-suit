from __future__ import annotations

from suitcode.core.action_models import ActionInvocation, ActionKind, ActionTargetKind, RepositoryAction
from suitcode.core.provenance_builders import heuristic_provenance, manifest_provenance, test_tool_provenance
from suitcode.providers.shared.actions.models import (
    ProviderActionKind,
    ProviderActionProvenanceKind,
    ProviderActionSpec,
    ProviderActionTargetKind,
)


class ProviderActionTranslator:
    def __init__(self, provider_id: str, default_test_tool: str) -> None:
        self._provider_id = provider_id
        self._default_test_tool = default_test_tool

    def to_repository_action(self, item: ProviderActionSpec) -> RepositoryAction:
        return RepositoryAction(
            id=item.action_id,
            name=item.display_name,
            kind=self._to_action_kind(item.kind),
            provider_id=self._provider_id,
            target_id=item.target_id,
            target_kind=self._to_target_kind(item.target_kind),
            owner_ids=item.owner_ids,
            invocation=ActionInvocation(argv=item.argv, cwd=item.cwd),
            dry_run_supported=item.dry_run_supported,
            provenance=(self._to_provenance(item),),
        )

    @staticmethod
    def _to_action_kind(kind: ProviderActionKind) -> ActionKind:
        if kind == ProviderActionKind.RUNNER:
            return ActionKind.RUNNER_EXECUTION
        if kind == ProviderActionKind.TEST:
            return ActionKind.TEST_EXECUTION
        return ActionKind.BUILD_EXECUTION

    @staticmethod
    def _to_target_kind(kind: ProviderActionTargetKind) -> ActionTargetKind:
        if kind == ProviderActionTargetKind.RUNNER:
            return ActionTargetKind.RUNNER
        if kind == ProviderActionTargetKind.TEST_DEFINITION:
            return ActionTargetKind.TEST_DEFINITION
        if kind == ProviderActionTargetKind.COMPONENT:
            return ActionTargetKind.COMPONENT
        return ActionTargetKind.REPOSITORY

    def _to_provenance(self, item: ProviderActionSpec):
        if item.provenance_kind == ProviderActionProvenanceKind.TEST_TOOL:
            source_tool = item.provenance_tool or self._default_test_tool
            return test_tool_provenance(
                source_tool=source_tool,
                evidence_summary=item.provenance_summary,
                evidence_paths=item.provenance_paths,
            )
        if item.provenance_kind == ProviderActionProvenanceKind.HEURISTIC:
            return heuristic_provenance(
                evidence_summary=item.provenance_summary,
                evidence_paths=item.provenance_paths,
            )
        return manifest_provenance(
            source_tool=item.provenance_tool,
            evidence_summary=item.provenance_summary,
            evidence_paths=item.provenance_paths,
        )
