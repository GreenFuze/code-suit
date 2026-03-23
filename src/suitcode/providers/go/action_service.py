from __future__ import annotations

from suitcode.providers.go.models import GoPackageAnalysis, GoTestAnalysis
from suitcode.providers.shared.actions import (
    ProviderActionKind,
    ProviderActionProvenanceKind,
    ProviderActionSpec,
    ProviderActionTargetKind,
)


class GoActionService:
    def discover(
        self,
        *,
        components: tuple[GoPackageAnalysis, ...],
        tests: tuple[GoTestAnalysis, ...],
    ) -> tuple[ProviderActionSpec, ...]:
        actions: list[ProviderActionSpec] = []
        component_ids = {component.import_path: f'component:go:{component.import_path}' for component in components}

        for test in tests:
            component_id = component_ids[test.import_path]
            actions.append(
                ProviderActionSpec(
                    action_id=f'action:go:test:{test.import_path}',
                    display_name=f'Run go test for `{test.import_path}`',
                    kind=ProviderActionKind.TEST,
                    target_id=test.test_id,
                    target_kind=ProviderActionTargetKind.TEST_DEFINITION,
                    owner_ids=(test.test_id, component_id),
                    argv=('go', 'test', '-buildvcs=false', test.import_path),
                    cwd=(test.module_root_rel_path or None),
                    dry_run_supported=True,
                    provenance_kind=ProviderActionProvenanceKind.TEST_TOOL,
                    provenance_tool='go test',
                    provenance_summary='derived from authoritative go package test discovery',
                    provenance_paths=test.evidence_paths,
                )
            )

        for component in components:
            if not component.is_main:
                continue
            component_id = component_ids[component.import_path]
            actions.append(
                ProviderActionSpec(
                    action_id=f'action:go:build:{component.import_path}',
                    display_name=f'Build go package `{component.import_path}`',
                    kind=ProviderActionKind.BUILD,
                    target_id=component_id,
                    target_kind=ProviderActionTargetKind.COMPONENT,
                    owner_ids=(component_id,),
                    argv=('go', 'build', '-buildvcs=false', component.import_path),
                    cwd=(component.module_root_rel_path or None),
                    dry_run_supported=True,
                    provenance_kind=ProviderActionProvenanceKind.MANIFEST,
                    provenance_tool='go list',
                    provenance_summary='derived from go package analysis for buildable main packages',
                    provenance_paths=(component.directory_rel_path, *component.go_files),
                )
            )

        by_id: dict[str, ProviderActionSpec] = {}
        for action in actions:
            if action.action_id in by_id:
                raise ValueError(f'duplicate go action id detected: `{action.action_id}`')
            by_id[action.action_id] = action
        return tuple(sorted(by_id.values(), key=lambda item: item.action_id))
