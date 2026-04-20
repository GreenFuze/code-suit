from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import get_type_hints

import pytest
from pydantic import TypeAdapter
from suitcode.core.build_service import BuildService
from suitcode.core.code.evidence_tier import CodeEvidenceTier
from suitcode.core.change_models import ChangeTarget
from suitcode.core.intelligence_models import (
    FileRelationshipKind,
    FileRelationshipRef,
    InvariantAccessKind,
    InvariantFindingKind,
    InvariantFindingRef,
    RenderEdgeKind,
    RenderEdgeRef,
    StaticFlowEdgeKind,
    StaticFlowEdgeRef,
)
from suitcode.core.provenance_builders import dependency_graph_provenance
from suitcode.core.runner_service import RunnerService
from suitcode.core.workspace import Workspace
from suitcode.mcp.errors import McpNotFoundError, McpRetryableError, McpUnsupportedRepositoryError, McpValidationError
from suitcode.mcp.models import (
    BatchChangeImpactTargetView,
    ChangeEvidencePreviewView,
    ChangeImpactView,
    FileOwnerView,
    FileRelationshipView,
    FileUnderstandingTargetView,
    FileView,
    InvariantFindingView,
    RenderEdgeView,
    LocationView,
    OwnerView,
    ProvenanceView,
    StrictModel,
    ToolTimingView,
    TruthCoverageByDomainView,
    TruthCoverageSummaryView,
)
from suitcode.mcp.service import SuitMcpService
from suitcode.mcp.state import WorkspaceRegistry
from suitcode.providers.npm.tool_runner import TypeScriptToolTimeoutError
from suitcode.providers.shared.action_execution import ActionExecutionResult, ActionExecutionStatus
from suitcode.runtime.errors import CoordinatorRuntimeNotReadyError, SemanticQueryTimeoutError
from suitcode.runtime.models import ManagedServerState, ServerFamily


class _TimingResult(StrictModel):
    timing: ToolTimingView | None = None


def _provenance_view(*paths: str) -> tuple[ProvenanceView, ...]:
    return (
        ProvenanceView(
            confidence_mode="high",
            source_kind="dependency_graph",
            source_tool="typescript",
            evidence_summary="deterministic test evidence",
            evidence_paths=paths or ("src/index.ts",),
        ),
    )


def test_read_only_repository_seam_attaches_agent_visible_timing() -> None:
    class _FakeRegistry:
        def __init__(self) -> None:
            self.calls = 0

        def open_repository(self, repository_path: str):
            self.calls += 1
            return type(
                "OpenState",
                (),
                {
                    "repository": object(),
                    "reused": self.calls > 1,
                },
            )()

    fake_registry = _FakeRegistry()
    service = SuitMcpService(read_only_registry=fake_registry)

    def _callback(_repository):
        return service._attach_agent_visible_timing("understand_file", _TimingResult())  # noqa: SLF001

    first = service._with_read_only_repository("repo", _callback, tool_name="understand_file")  # noqa: SLF001
    second = service._with_read_only_repository("repo", _callback, tool_name="understand_file")  # noqa: SLF001

    assert first.timing is not None
    assert first.timing.repository_reused is False
    assert second.timing is not None
    assert second.timing.repository_reused is True
    assert tuple(stage.name for stage in second.timing.stages) == ("repository_acquire",)


def test_service_open_workspace_and_list_repositories(service: SuitMcpService, npm_repo_root: Path) -> None:
    opened = service.open_workspace(str(npm_repo_root))
    repositories = service.list_workspace_repositories(opened.workspace.workspace_id)

    assert opened.reused is False
    assert opened.workspace.repository_count == 1
    assert opened.initial_repository.root_path == str(npm_repo_root)
    assert opened.initial_repository.provider_ids == ("go", "npm", "python")
    assert opened.initial_repository.provider_attachment_roots["npm"] == (".",)
    assert opened.initial_repository.provider_attachment_roots["python"] == ("tools/codegen",)
    assert opened.guidance.session_scope == "process_local"
    assert "process" in opened.guidance.message.lower()
    assert "repository_summary" in opened.guidance.recommended_next_calls
    assert "repository_summary_by_path" in opened.guidance.read_only_alternatives
    assert repositories.total == 1


def test_service_core_tools_reuse_existing_repository_intelligence(
    service: SuitMcpService,
    npm_repo_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(service, "_wait_for_repository_warmup", lambda repository: None)
    understanding = service.understand_repository(str(npm_repo_root), preview_limit=5)
    file_understanding = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
        detail_level="full",
    )
    impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        detail_level="full",
    )
    minimum = service.what_should_i_run(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )
    proof_gaps = service.what_is_not_proven(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )
    availability = service.can_i_do_this(
        str(npm_repo_root),
        "packages/core/src/index.ts",
        "test",
    )

    assert understanding.repository.component_count >= 1
    assert understanding.truth_coverage.domains
    assert understanding.provenance
    assert understanding.timing is not None
    assert understanding.timing.repository_reused is False
    assert any(stage.name == "repository_acquire" for stage in understanding.timing.stages)
    assert file_understanding.target_count == 1
    assert file_understanding.targets[0].file_owner.owner.id == "component:npm:@monorepo/core"
    assert file_understanding.targets[0].reference_site_count >= 1
    assert file_understanding.targets[0].reference_sites_preview
    assert file_understanding.aggregate_related_tests
    assert file_understanding.provenance
    assert file_understanding.timing is not None
    assert file_understanding.timing.repository_reused is True
    assert file_understanding.timing.slow_targets
    assert impact.target_count == 1
    assert impact.targets[0].impact.target_kind == "file"
    assert impact.reference_sites
    assert impact.provenance
    assert impact.timing is not None
    assert impact.timing.repository_reused is True
    assert impact.timing.slow_targets
    assert minimum.target_count == 1
    assert minimum.compact_summary.required_validation_count >= 1
    assert minimum.targets[0].change_set.owner.id == "component:npm:@monorepo/core"
    assert minimum.timing is not None
    assert minimum.timing.repository_reused is True
    assert proof_gaps.target_count == 1
    assert proof_gaps.timing is not None
    assert proof_gaps.timing.repository_reused is True
    assert availability.supported is True
    assert "test" in availability.available_action_kinds
    assert availability.provenance
    assert not hasattr(availability, "timing")


def test_wait_for_repository_warmup_uses_project_coordinator_client(
    service: SuitMcpService,
    npm_repo_root: Path,
    monkeypatch,
) -> None:
    calls: list[object] = []

    class _FakeCoordinatorClient:
        def __init__(self, project_root: Path) -> None:
            calls.append(project_root)

        def wait_for_project_warmup(self, *, timeout_seconds: float | None = 90.0):
            calls.append(timeout_seconds)
            return None

    fake_repository = type("Repository", (), {"root": npm_repo_root.resolve()})()
    monkeypatch.setattr("suitcode.mcp.service.ProjectCoordinatorClient", _FakeCoordinatorClient)

    service._wait_for_repository_warmup(fake_repository)  # noqa: SLF001

    assert calls == [npm_repo_root.resolve(), None]


def test_service_core_tools_default_to_compact_detail_level(service: SuitMcpService, npm_repo_root: Path) -> None:
    file_understanding = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
    )
    impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )

    assert file_understanding.detail_level == "compact"
    assert not hasattr(file_understanding, "provenance")
    assert hasattr(file_understanding.targets[0], "top_validations")
    assert hasattr(file_understanding.targets[0], "decision_summary")
    assert impact.detail_level == "compact"
    assert not hasattr(impact, "provenance")
    assert hasattr(impact.targets[0], "top_impacted_files")
    assert hasattr(impact.targets[0], "decision_summary")


def test_core_tools_reject_invalid_detail_level(service: SuitMcpService, npm_repo_root: Path) -> None:
    with pytest.raises(McpValidationError, match="detail_level must be one of"):
        service.understand_file(
            str(npm_repo_root),
            ("packages/core/src/index.ts",),
            detail_level="verbose",
        )

    with pytest.raises(McpValidationError, match="detail_level must be one of"):
        service.what_changes_if_i_edit_this(
            str(npm_repo_root),
            ("packages/core/src/index.ts",),
            detail_level="verbose",
        )


def test_compact_detail_levels_materially_reduce_payload_size(service: SuitMcpService, npm_repo_root: Path) -> None:
    compact_file = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
        detail_level="compact",
    )
    standard_file = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
        detail_level="standard",
    )
    full_file = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
        detail_level="full",
    )
    compact_impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        detail_level="compact",
    )
    standard_impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        detail_level="standard",
    )
    full_impact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        detail_level="full",
    )

    assert len(compact_file.model_dump_json()) < len(standard_file.model_dump_json()) < len(full_file.model_dump_json())
    assert len(compact_impact.model_dump_json()) < len(standard_impact.model_dump_json()) < len(full_impact.model_dump_json())


def test_standard_understand_file_serialized_payload_validates_against_declared_return_type(
    service: SuitMcpService,
    npm_repo_root: Path,
) -> None:
    result = service.understand_file(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        related_test_limit=5,
        detail_level="standard",
    )
    payload = result.model_dump(mode="json")
    adapter = TypeAdapter(get_type_hints(SuitMcpService.understand_file)["return"])

    validated = adapter.validate_python(payload)

    assert validated.detail_level == "standard"


def test_standard_change_impact_serialized_payload_validates_against_declared_return_type(
    service: SuitMcpService,
    npm_repo_root: Path,
) -> None:
    result = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
        detail_level="standard",
    )
    payload = result.model_dump(mode="json")
    adapter = TypeAdapter(get_type_hints(SuitMcpService.what_changes_if_i_edit_this)["return"])

    validated = adapter.validate_python(payload)

    assert validated.detail_level == "standard"


def test_read_only_by_path_tools_match_workspace_tools_without_registry_mutation(service: SuitMcpService, npm_repo_root: Path) -> None:
    shutil.rmtree(npm_repo_root / ".suit", ignore_errors=True)
    assert not (npm_repo_root / ".suit").exists()
    assert service.list_open_workspaces().total == 0

    summary_by_path = service.repository_summary_by_path(str(npm_repo_root), preview_limit=5)
    owner_by_path = service.get_file_owner_by_path(str(npm_repo_root), "packages/core/src/index.ts")
    related_by_path = service.get_related_tests_by_path(
        str(npm_repo_root),
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    change_set_by_path = service.get_minimum_verified_change_set_by_path(
        str(npm_repo_root),
        repository_rel_path="packages/core/src/index.ts",
    )

    assert service.list_open_workspaces().total == 0
    assert not (npm_repo_root / ".suit").exists()

    opened = service.open_workspace(str(npm_repo_root))
    workspace_id = opened.workspace.workspace_id
    repository_id = opened.initial_repository.repository_id

    summary = service.repository_summary(workspace_id, repository_id, preview_limit=5)
    owner = service.get_file_owner(workspace_id, repository_id, "packages/core/src/index.ts")
    related = service.get_related_tests(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    change_set = service.get_minimum_verified_change_set(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert summary_by_path.model_dump() == summary.model_dump()
    assert owner_by_path.model_dump() == owner.model_dump()
    assert related_by_path.model_dump() == related.model_dump()
    assert change_set_by_path.model_dump() == change_set.model_dump()


def test_read_only_by_path_tools_reuse_process_local_repository(monkeypatch, npm_repo_root: Path) -> None:
    workspace_creations: list[Path] = []

    class _CountingWorkspace(Workspace):
        def __init__(self, repository_directory: Path, *, materialize_suit_dir: bool = True) -> None:
            workspace_creations.append(Path(repository_directory).resolve())
            super().__init__(repository_directory, materialize_suit_dir=materialize_suit_dir)

    monkeypatch.setattr("suitcode.mcp.state.Workspace", _CountingWorkspace)
    service = SuitMcpService(registry=WorkspaceRegistry())
    monkeypatch.setattr(service, "_wait_for_repository_warmup", lambda repository: None)

    service.repository_summary_by_path(str(npm_repo_root), preview_limit=5)
    service.what_should_i_run(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )
    service.what_is_not_proven(
        str(npm_repo_root),
        ("packages/core/src/index.ts",),
    )

    assert workspace_creations == [npm_repo_root.resolve()]


def test_read_only_by_path_tools_validate_and_map_errors(service: SuitMcpService, npm_repo_root: Path, tmp_path: Path) -> None:
    with pytest.raises(McpValidationError):
        service.repository_summary_by_path(str(npm_repo_root), preview_limit=0)

    with pytest.raises(McpValidationError):
        service.get_related_tests_by_path(str(npm_repo_root))

    with pytest.raises(McpValidationError):
        service.get_minimum_verified_change_set_by_path(str(npm_repo_root))

    with pytest.raises(McpNotFoundError):
        service.get_file_owner_by_path(str(npm_repo_root), "missing/file.ts")

    unsupported_root = tmp_path / "repo"
    unsupported_root.mkdir()
    (unsupported_root / ".git").mkdir()

    with pytest.raises(McpUnsupportedRepositoryError):
        service.repository_summary_by_path(str(unsupported_root))


def test_file_target_tools_report_missing_file_with_exact_siblings(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend-missing"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "GamePlayerPage.tsx").write_text(
        "export const GamePlayerPage = () => null;\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "PlayPage.tsx").write_text(
        "export const PlayPage = () => null;\n",
        encoding="utf-8",
    )

    expected_fragments = (
        "repository file not found: `src/pages/BrowserPlayPage.tsx`",
        "Exact file siblings in `src/pages`",
        "`GamePlayerPage.tsx`",
        "`PlayPage.tsx`",
    )

    with pytest.raises(McpNotFoundError, match="repository file not found"):
        service.get_file_owner_by_path(str(repo_root), "src/pages/BrowserPlayPage.tsx")
    with pytest.raises(McpValidationError, match="repository file not found"):
        service.understand_file(str(repo_root), ("src/pages/BrowserPlayPage.tsx",))
    with pytest.raises(McpValidationError, match="repository file not found"):
        service.what_changes_if_i_edit_this(str(repo_root), ("src/pages/BrowserPlayPage.tsx",))
    with pytest.raises(McpValidationError, match="repository file not found"):
        service.what_should_i_run(str(repo_root), ("src/pages/BrowserPlayPage.tsx",))
    with pytest.raises(McpValidationError, match="repository file not found"):
        service.can_i_do_this(str(repo_root), "src/pages/BrowserPlayPage.tsx", "build")

    for call in (
        lambda: service.get_file_owner_by_path(str(repo_root), "src/pages/BrowserPlayPage.tsx"),
        lambda: service.understand_file(str(repo_root), ("src/pages/BrowserPlayPage.tsx",)),
        lambda: service.what_changes_if_i_edit_this(str(repo_root), ("src/pages/BrowserPlayPage.tsx",)),
        lambda: service.what_should_i_run(str(repo_root), ("src/pages/BrowserPlayPage.tsx",)),
        lambda: service.can_i_do_this(str(repo_root), "src/pages/BrowserPlayPage.tsx", "build"),
    ):
        with pytest.raises((McpNotFoundError, McpValidationError)) as exc_info:
            call()
        text = str(exc_info.value)
        for fragment in expected_fragments:
            assert fragment in text


def test_file_target_tools_report_directory_targets_cleanly(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend-directory"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "GamePlayerPage.tsx").write_text(
        "export const GamePlayerPage = () => null;\n",
        encoding="utf-8",
    )

    with pytest.raises(McpValidationError, match="is a directory, not a file"):
        service.understand_file(str(repo_root), ("src/pages",))


def test_workspace_file_target_tools_report_missing_file_with_exact_siblings(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend-workspace-missing"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "GamePlayerPage.tsx").write_text(
        "export const GamePlayerPage = () => null;\n",
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "PlayPage.tsx").write_text(
        "export const PlayPage = () => null;\n",
        encoding="utf-8",
    )

    opened = service.open_workspace(str(repo_root))
    workspace_id = opened.workspace.workspace_id
    repository_id = opened.initial_repository.repository_id

    for call in (
        lambda: service.describe_files(workspace_id, repository_id, ("src/pages/BrowserPlayPage.tsx",)),
        lambda: service.get_related_tests(workspace_id, repository_id, repository_rel_path="src/pages/BrowserPlayPage.tsx"),
        lambda: service.analyze_impact(workspace_id, repository_id, repository_rel_path="src/pages/BrowserPlayPage.tsx"),
        lambda: service.analyze_change(workspace_id, repository_id, repository_rel_path="src/pages/BrowserPlayPage.tsx"),
        lambda: service.get_minimum_verified_change_set(
            workspace_id,
            repository_id,
            repository_rel_path="src/pages/BrowserPlayPage.tsx",
        ),
    ):
        with pytest.raises((McpNotFoundError, McpValidationError)) as exc_info:
            call()
        text = str(exc_info.value)
        assert "repository file not found: `src/pages/BrowserPlayPage.tsx`" in text
        assert "Exact file siblings in `src/pages`" in text
        assert "`GamePlayerPage.tsx`" in text
        assert "`PlayPage.tsx`" in text


def test_understand_file_supports_standalone_npm_package_root(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")

    understanding = service.understand_file(
        str(repo_root),
        ("src/pages/LibraryPage.tsx",),
        related_test_limit=5,
    )

    assert understanding.targets[0].file_owner.owner.id == "component:npm:frontend"


def test_understand_file_supports_standalone_npm_public_runtime_asset(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "public" / "runtimes" / "demo").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    (repo_root / "public" / "runtimes" / "demo" / "runtime.js").write_text("console.log('runtime');\n", encoding="utf-8")

    understanding = service.understand_file(
        str(repo_root),
        ("public/runtimes/demo/runtime.js",),
        related_test_limit=5,
    )

    assert understanding.targets[0].file_owner.owner.id == "component:npm:frontend"


def test_understand_repository_accepts_larger_preview_limit(
    service: SuitMcpService,
    npm_repo_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(service, "_wait_for_repository_warmup", lambda repository: None)
    understanding = service.understand_repository(str(npm_repo_root), preview_limit=50)

    assert understanding.repository.preview_limit == 50


def test_understand_file_reports_unowned_artifacts_clearly(service: SuitMcpService, npm_repo_root: Path) -> None:
    (npm_repo_root / "notes.txt").write_text("plain text\n", encoding="utf-8")

    with pytest.raises(McpValidationError, match="provider-owned files"):
        service.understand_file(
            str(npm_repo_root),
            ("notes.txt",),
        )


def test_understand_file_returns_markdown_structure(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "docs-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "roadmap.md").write_text(
        "---\n"
        "title: Roadmap\n"
        "owner: docs\n"
        "---\n\n"
        "# Plan\n\n"
        "See [tracking](docs/tracking.md).\n\n"
        "- [x] discovery\n"
        "- [ ] rollout\n\n"
        "## Commands\n\n"
        "```bash\n"
        "npm run build\n"
        "```\n",
        encoding="utf-8",
    )

    understanding = service.understand_file(
        str(repo_root),
        ("roadmap.md",),
        related_test_limit=5,
    )

    target = understanding.targets[0]
    assert target.file_owner.owner.id == "component:markdown:documents"
    assert target.structured_artifact is not None
    assert target.structured_artifact.artifact_kind == "markdown_document"
    assert target.structured_artifact.markdown is not None
    assert target.structured_artifact.markdown.section_count == 2
    assert target.structured_artifact.markdown.sections[0].heading == "Plan"
    assert target.structured_artifact.markdown.sections[0].line_start == 6
    assert target.structured_artifact.markdown.sections[1].heading == "Commands"
    assert target.structured_artifact.markdown.code_block_count == 1
    assert target.structured_artifact.markdown.links[0].destination == "docs/tracking.md"
    assert target.structured_artifact.markdown.frontmatter is not None
    assert target.structured_artifact.markdown.frontmatter.keys == ("title", "owner")
    assert target.structured_artifact.markdown.checklist_item_count == 2
    assert understanding.suggested_follow_ups == tuple()


def test_understand_file_compact_shapes_large_markdown_checklists(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "docs-compact"
    (repo_root / ".git").mkdir(parents=True)
    checklist = "".join(f"- [ ] item {index}\n" for index in range(1, 9))
    (repo_root / "roadmap.md").write_text(
        "# Checklist\n\n"
        f"{checklist}",
        encoding="utf-8",
    )

    compact = service.understand_file(
        str(repo_root),
        ("roadmap.md",),
        detail_level="compact",
    )
    full = service.understand_file(
        str(repo_root),
        ("roadmap.md",),
        detail_level="full",
    )

    compact_markdown = compact.targets[0].structured_artifact.markdown
    full_markdown = full.targets[0].structured_artifact.markdown

    assert compact_markdown is not None
    assert full_markdown is not None
    assert compact_markdown.checklist_item_count == 8
    assert len(compact_markdown.checklist_items) == 3
    assert len(full_markdown.checklist_items) == 8


def test_understand_file_returns_openapi_structure(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "api-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "openapi.yaml").write_text(
        "openapi: 3.1.0\n"
        "tags:\n"
        "  - name: scan\n"
        "paths:\n"
        "  /scan/jobs:\n"
        "    get:\n"
        "      operationId: listScanJobs\n"
        "components:\n"
        "  schemas:\n"
        "    ScanJob:\n"
        "      type: object\n",
        encoding="utf-8",
    )

    understanding = service.understand_file(
        str(repo_root),
        ("openapi.yaml",),
        related_test_limit=5,
    )

    target = understanding.targets[0]
    assert target.file_owner.owner.id == "component:openapi:specs"
    assert target.structured_artifact is not None
    assert target.structured_artifact.artifact_kind == "openapi_document"
    assert target.structured_artifact.openapi is not None
    assert target.structured_artifact.openapi.spec_version == "3.1.0"
    assert target.structured_artifact.openapi.path_count == 1
    assert target.structured_artifact.openapi.operations[0].path == "/scan/jobs"
    assert target.structured_artifact.openapi.operations[0].method == "get"
    assert target.structured_artifact.openapi.operations[0].operation_id == "listScanJobs"
    assert target.structured_artifact.openapi.schema_count == 1
    assert target.structured_artifact.openapi.schemas[0].name == "ScanJob"
    assert target.structured_artifact.openapi.tag_count == 1
    assert target.structured_artifact.openapi.tags[0].name == "scan"
    assert understanding.suggested_follow_ups == tuple()


def test_frontend_standalone_package_surfaces_build_script_as_action(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src" / "pages").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build",
            "dev": "vite"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "pages" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/pages/LibraryPage.tsx",),
    )
    availability = service.can_i_do_this(
        str(repo_root),
        repository_rel_path="src/pages/LibraryPage.tsx",
        requested_action_kind="build",
    )

    assert [item.action_id for item in minimum.build_targets] == ["action:npm:build:frontend"]
    assert minimum.build_targets[0].invocation.argv_preview == ("npm", "run", "build")
    assert any(item.reason_code == "no_deterministic_test_targets_available" for item in minimum.excluded_items)
    assert availability.supported is True
    assert "build" in availability.available_action_kinds


def test_build_only_frontend_summary_includes_exact_build_proof_facets(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/App.tsx",),
    )

    assert minimum.compact_summary.required_validation[0].item_kind == "build_target"
    assert "TypeScript typecheck" in minimum.compact_summary.required_validation[0].summary
    assert "frontend bundle build" in minimum.compact_summary.required_validation[0].summary
    assert any(
        "no finer deterministic frontend test target was discovered" in item.summary
        for item in minimum.compact_summary.exclusions
    )


def test_frontend_compact_surfaces_decision_first_build_only_proof(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-proof"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")

    file_understanding = service.understand_file(
        str(repo_root),
        ("src/App.tsx",),
        detail_level="compact",
    )
    impact = service.what_changes_if_i_edit_this(
        str(repo_root),
        ("src/App.tsx",),
        detail_level="compact",
    )

    file_target = file_understanding.targets[0]
    impact_target = impact.targets[0]

    assert [item.item_kind for item in file_target.top_validations] == ["build_target"]
    assert "TypeScript typecheck" in file_target.top_validations[0].summary
    assert {item.risk_code for item in file_target.top_risks} >= {
        "build_only_validation",
        "public_surface_touched",
    }
    assert hasattr(file_target, "frontend_proof_summary") is False
    assert len(file_target.decision_summary) >= 3

    assert [item.item_kind for item in impact_target.top_validations] == ["build_target"]
    assert "frontend bundle build" in impact_target.top_validations[0].summary
    assert {item.risk_code for item in impact_target.top_risks} >= {
        "build_only_validation",
        "public_surface_touched",
    }
    assert hasattr(impact_target, "frontend_proof_summary") is False
    assert len(impact_target.decision_summary) >= 3


def test_what_is_not_proven_reports_build_only_frontend_gap(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-proof-gaps"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")

    proof = service.what_is_not_proven(
        str(repo_root),
        ("src/App.tsx",),
    )

    target = proof.targets[0]
    assert target.validation_is_build_only is True
    assert target.has_focused_test_surface is False
    assert {item.gap_code for item in target.gap_items} >= {
        "build_only_frontend_surface",
        "no_focused_test_surface",
    }
    assert proof.highest_priority_targets == ("src/App.tsx",)


def test_what_is_not_proven_reports_focused_backend_test_surface(
    service: SuitMcpService,
    go_repo_root: Path,
) -> None:
    proof = service.what_is_not_proven(
        str(go_repo_root),
        ("internal/service/service.go",),
    )

    target = proof.targets[0]
    assert target.has_focused_test_surface is True
    assert "no_focused_test_surface" not in {item.gap_code for item in target.gap_items}
    assert target.current_validation_surfaces


def test_what_is_not_proven_reports_artifact_member_without_validation_surface(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "artifact-proof-gaps"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "public" / "runtimes").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
    (repo_root / "public" / "runtimes" / "bundle.js").write_text("console.log('bundle');\n", encoding="utf-8")

    proof = service.what_is_not_proven(
        str(repo_root),
        ("public/runtimes/bundle.js",),
    )

    target = proof.targets[0]
    assert target.current_validation_surfaces == tuple()
    assert {item.gap_code for item in target.gap_items} >= {
        "no_deterministic_validation_surface",
        "artifact_member_without_validation_surface",
        "no_focused_test_surface",
    }


def test_compact_grouped_file_understanding_returns_decision_first_targets(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    understanding = service.understand_file(
        str(repo_root),
        tuple(f"src/{name}" for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx")),
        detail_level="compact",
    )

    assert understanding.target_count == 4
    assert understanding.completed_target_count == 4
    assert all(target.top_validations for target in understanding.targets)
    assert all(target.decision_summary for target in understanding.targets)
    assert all(hasattr(target, "implementation_flow_summary") is False for target in understanding.targets)


def test_compact_grouped_change_impact_returns_decision_first_targets(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-impact-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    for name in ("A.tsx", "B.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    impact = service.what_changes_if_i_edit_this(
        str(repo_root),
        tuple(f"src/{name}" for name in ("A.tsx", "B.tsx")),
        detail_level="compact",
    )

    assert impact.target_count == 2
    assert impact.completed_target_count == 2
    assert all(target.top_validations for target in impact.targets)
    assert all(target.decision_summary for target in impact.targets)
    assert all(hasattr(target, "implementation_flow_summary") is False for target in impact.targets)


def test_collect_batch_results_returns_partial_results_when_one_target_times_out(
    service: SuitMcpService,
    monkeypatch,
) -> None:
    monkeypatch.setattr(service, "_BATCH_COMPACT_TARGET_TIMEOUT_SECONDS", 0.1)

    def _build(repository_rel_path: str) -> str:
        if repository_rel_path == "slow":
            time.sleep(0.3)
        return repository_rel_path

    completed, incomplete = service._collect_batch_results(
        repository_rel_paths=("fast", "slow"),
        build_target=_build,
        tool_name="understand_file",
        detail_level="compact",
        allow_parallel=True,
    )

    assert completed == ("fast",)
    assert len(incomplete) == 1
    assert incomplete[0].repository_rel_path == "slow"
    assert incomplete[0].reason_code == "analysis_timeout"


def test_compact_grouped_understand_file_surfaces_partial_results(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "frontend-partial-file"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("Fast.tsx", "Slow.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    original = service._understand_file_target(
        Workspace(repo_root).repositories[0],
        "src/Fast.tsx",
        related_test_limit=3,
        detail_level="compact",
        include_reference_sites=False,
        include_implementation_locations=False,
        enable_implementation_flow=False,
        enable_hot_entrypoints=False,
        reference_site_limit=3,
        evidence_tier=service._code_evidence_tier("compact", 2),
    )
    incomplete = service._incomplete_batch_target_view(
        "src/Slow.tsx",
        reason_code="analysis_timeout",
        message="understand_file exceeded the grouped compact per-target timeout",
    )

    monkeypatch.setattr(
        service,
        "_collect_understand_file_targets",
        lambda **kwargs: ((original,), (incomplete,)),
    )

    understanding = service.understand_file(
        str(repo_root),
        ("src/Fast.tsx", "src/Slow.tsx"),
        detail_level="compact",
    )

    assert understanding.target_count == 2
    assert understanding.completed_target_count == 1
    assert len(understanding.targets) == 1
    assert understanding.incomplete_targets == (incomplete,)


def test_compact_grouped_change_impact_surfaces_partial_results(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "frontend-partial-impact"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("Fast.tsx", "Slow.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    repository = Workspace(repo_root).repositories[0]
    change = repository.analyze_change(
        ChangeTarget(repository_rel_path="src/Fast.tsx"),
        reference_preview_limit=3,
        dependent_preview_limit=3,
        test_preview_limit=3,
        runner_preview_limit=3,
        include_reference_locations=False,
        include_implementation_locations=False,
        evidence_tier=service._code_evidence_tier("compact", 2),
    )
    target = BatchChangeImpactTargetView(
        repository_rel_path="src/Fast.tsx",
        impact=service._change_impact_presenter.change_impact_view(change),
        implementation_flow_summary=None,
        frontend_proof_summary=service._frontend_proof_summary_view(repository, "src/Fast.tsx"),
        artifact_surface_summary=None,
    )
    incomplete = service._incomplete_batch_target_view(
        "src/Slow.tsx",
        reason_code="analysis_timeout",
        message="what_changes_if_i_edit_this exceeded the grouped compact per-target timeout",
    )

    monkeypatch.setattr(
        service,
        "_collect_change_impact_targets",
        lambda **kwargs: ((target,), (incomplete,)),
    )

    impact = service.what_changes_if_i_edit_this(
        str(repo_root),
        ("src/Fast.tsx", "src/Slow.tsx"),
        detail_level="compact",
    )

    assert impact.target_count == 2
    assert impact.completed_target_count == 1
    assert len(impact.targets) == 1
    assert impact.incomplete_targets == (incomplete,)


def test_compact_single_target_large_file_prefers_structural_understand_file(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "large-compact-file"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    (repo_root / "src" / "Large.tsx").write_text("export const Large = () => null;\n", encoding="utf-8")

    monkeypatch.setattr(SuitMcpService, "_COMPACT_SINGLE_TARGET_STRUCTURAL_LINE_THRESHOLD", 0)
    observed: dict[str, object] = {}

    def _capture(**kwargs):
        observed.update(kwargs)
        return tuple(), tuple()

    monkeypatch.setattr(service, "_collect_understand_file_targets", _capture)
    monkeypatch.setattr(service, "_compact_file_understanding_view", lambda *args, **kwargs: {"ok": True})

    result = service.understand_file(
        str(repo_root),
        ("src/Large.tsx",),
        detail_level="compact",
    )

    assert result == {"ok": True}
    assert observed["evidence_tier"] == CodeEvidenceTier.STRUCTURAL
    assert observed["include_reference_sites"] is False
    assert observed["include_implementation_locations"] is False
    assert observed["enable_implementation_flow"] is False
    assert observed["enable_hot_entrypoints"] is False


def test_compact_single_target_large_file_prefers_structural_change_impact(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "large-compact-impact"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    (repo_root / "src" / "Large.tsx").write_text("export const Large = () => null;\n", encoding="utf-8")

    monkeypatch.setattr(SuitMcpService, "_COMPACT_SINGLE_TARGET_STRUCTURAL_LINE_THRESHOLD", 0)
    observed: dict[str, object] = {}

    def _capture(**kwargs):
        observed.update(kwargs)
        return tuple(), tuple()

    monkeypatch.setattr(service, "_collect_change_impact_targets", _capture)
    monkeypatch.setattr(service, "_compact_change_impact_view", lambda *args, **kwargs: {"ok": True})

    result = service.what_changes_if_i_edit_this(
        str(repo_root),
        ("src/Large.tsx",),
        detail_level="compact",
    )

    assert result == {"ok": True}
    assert observed["evidence_tier"] == CodeEvidenceTier.STRUCTURAL
    assert observed["include_reference_locations"] is False
    assert observed["include_implementation_locations"] is False
    assert observed["enable_deep_symbol_navigation"] is False


def test_compact_single_target_small_file_keeps_semantic_understand_file(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "small-compact-file"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    (repo_root / "src" / "Small.tsx").write_text("export const Small = () => null;\n", encoding="utf-8")

    monkeypatch.setattr(SuitMcpService, "_COMPACT_SINGLE_TARGET_STRUCTURAL_LINE_THRESHOLD", 100)
    monkeypatch.setattr(SuitMcpService, "_COMPACT_SINGLE_TARGET_STRUCTURAL_BYTE_THRESHOLD", 100000)
    observed: dict[str, object] = {}

    def _capture(**kwargs):
        observed.update(kwargs)
        return tuple(), tuple()

    monkeypatch.setattr(service, "_collect_understand_file_targets", _capture)
    monkeypatch.setattr(service, "_compact_file_understanding_view", lambda *args, **kwargs: {"ok": True})

    result = service.understand_file(
        str(repo_root),
        ("src/Small.tsx",),
        detail_level="compact",
    )

    assert result == {"ok": True}
    assert observed["evidence_tier"] == CodeEvidenceTier.SEMANTIC
    assert observed["include_reference_sites"] is True
    assert observed["include_implementation_locations"] is True
    assert observed["enable_implementation_flow"] is True
    assert observed["enable_hot_entrypoints"] is True


def test_standard_detail_level_rejects_broad_understand_file_batches(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-standard-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    with pytest.raises(McpValidationError, match="detail_level=standard supports at most 3 targets"):
        service.understand_file(
            str(repo_root),
            tuple(f"src/{name}" for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx")),
            detail_level="standard",
        )


def test_standard_detail_level_rejects_broad_change_impact_batches(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-standard-impact-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    with pytest.raises(McpValidationError, match="detail_level=standard supports at most 3 targets"):
        service.what_changes_if_i_edit_this(
            str(repo_root),
            tuple(f"src/{name}" for name in ("A.tsx", "B.tsx", "C.tsx", "D.tsx")),
            detail_level="standard",
        )


def test_understand_file_runtime_warming_maps_to_retryable_error(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    expected = (
        "runtime_not_ready: "
        "tool=understand_file "
        "server=gopls "
        "attachment_root=C:\\\\repo "
        "state=warming "
        "retry_after_seconds=15 "
        "attempted_retries=3 "
        "max_attempts=3 "
        "retry_exhausted=true; "
        "SuitCode retried internally and the runtime is still not ready. "
        "Narrow to 1 target or use detail_level=compact."
    )

    class _Repo:
        def describe_files(self, *args, **kwargs):
            raise CoordinatorRuntimeNotReadyError(
                server_family=ServerFamily.GOPLS,
                attachment_root="C:\\repo",
                state=ManagedServerState.WARMING,
                retry_after_seconds=15,
            )

    with pytest.raises(McpRetryableError, match=expected):
        service._understand_file_target(  # noqa: SLF001
            _Repo(),
            "src/GamePlayerPage.tsx",
            related_test_limit=5,
            detail_level="standard",
            include_reference_sites=True,
            include_implementation_locations=True,
            enable_implementation_flow=True,
            enable_hot_entrypoints=True,
            reference_site_limit=None,
            evidence_tier=CodeEvidenceTier.SEMANTIC,
        )


def test_read_only_repository_preserves_retryable_errors(service: SuitMcpService, monkeypatch) -> None:
    class _OpenState:
        repository = object()

    monkeypatch.setattr(service._read_only_registry, "open_repository", lambda repository_path: _OpenState())  # noqa: SLF001

    with pytest.raises(McpRetryableError, match="retryable"):
        service._with_read_only_repository(  # noqa: SLF001
            r"C:\repo",
            lambda repository: (_ for _ in ()).throw(McpRetryableError("retryable")),
            tool_name="understand_repository",
        )


def test_read_only_repository_maps_raw_runtime_errors_to_retryable_error(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)

    class _OpenState:
        repository = object()

    monkeypatch.setattr(service._read_only_registry, "open_repository", lambda repository_path: _OpenState())  # noqa: SLF001

    with pytest.raises(
        McpRetryableError,
        match=(
            "runtime_not_ready: "
            "tool=understand_repository "
            "server=gopls "
            "attachment_root=C:\\\\repo "
            "state=warming "
            "retry_after_seconds=15 "
            "attempted_retries=3 "
            "max_attempts=3 "
            "retry_exhausted=true"
        ),
    ):
        service._with_read_only_repository(  # noqa: SLF001
            r"C:\repo",
            lambda repository: (_ for _ in ()).throw(
                CoordinatorRuntimeNotReadyError(
                    server_family=ServerFamily.GOPLS,
                    attachment_root=r"C:\repo",
                    state=ManagedServerState.WARMING,
                    retry_after_seconds=15,
                )
            ),
            tool_name="understand_repository",
        )


def test_change_impact_runtime_warming_maps_to_retryable_error(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    expected = (
        "runtime_not_ready: "
        "tool=what_changes_if_i_edit_this "
        "server=gopls "
        "attachment_root=C:\\\\repo "
        "state=warming "
        "retry_after_seconds=15 "
        "attempted_retries=3 "
        "max_attempts=3 "
        "retry_exhausted=true; "
        "SuitCode retried internally and the runtime is still not ready. "
        "Narrow to 1 target or use detail_level=compact."
    )

    class _Repo:
        def analyze_change(self, *args, **kwargs):
            raise CoordinatorRuntimeNotReadyError(
                server_family=ServerFamily.GOPLS,
                attachment_root="C:\\repo",
                state=ManagedServerState.WARMING,
                retry_after_seconds=15,
            )

    with pytest.raises(McpRetryableError, match=expected):
        service._collect_change_impact_targets(  # noqa: SLF001
            repository=_Repo(),
            repository_rel_paths=("server/internal/scan/manual_review_service.go",),
            detail_level="standard",
            reference_preview_limit=10,
            dependent_preview_limit=10,
            test_preview_limit=10,
            runner_preview_limit=10,
            include_reference_locations=True,
            include_implementation_locations=True,
            evidence_tier=CodeEvidenceTier.SEMANTIC,
            enable_deep_symbol_navigation=True,
        )


def test_understand_file_typescript_tool_timeout_maps_to_retryable_error(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    expected = (
        "runtime_not_ready: "
        "tool=understand_file "
        "server=typescript-tooling "
        "attachment_root=C:\\\\repo\\\\server\\\\frontend "
        "state=degraded "
        "retry_after_seconds=15 "
        "attempted_retries=3 "
        "max_attempts=3 "
        "retry_exhausted=true; "
        "SuitCode retried internally and the runtime is still not ready. "
        "Narrow to 1 target or use detail_level=compact."
    )

    class _Repo:
        def describe_files(self, *args, **kwargs):
            raise TypeScriptToolTimeoutError(
                attachment_root=Path(r"C:\repo\server\frontend"),
                script_name="ts_static_analysis.cjs",
            )

    with pytest.raises(McpRetryableError, match=expected):
        service._understand_file_target(  # noqa: SLF001
            _Repo(),
            "src/GameDetailPage.tsx",
            related_test_limit=1,
            detail_level="standard",
            include_reference_sites=True,
            include_implementation_locations=True,
            enable_implementation_flow=True,
            enable_hot_entrypoints=True,
            reference_site_limit=None,
            evidence_tier=CodeEvidenceTier.SEMANTIC,
        )


def test_understand_file_semantic_query_timeout_maps_to_retryable_error(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    expected = (
        "runtime_not_ready: "
        "tool=understand_file "
        "server=typescript-language-server "
        "attachment_root=C:\\\\repo "
        "state=degraded "
        "retry_after_seconds=15 "
        "attempted_retries=3 "
        "max_attempts=3 "
        "retry_exhausted=true; "
        "SuitCode retried internally and the runtime is still not ready. "
        "Narrow to 1 target or use detail_level=compact."
    )

    class _Repo:
        def describe_files(self, *args, **kwargs):
            raise SemanticQueryTimeoutError(
                server_name="typescript-language-server",
                attachment_root=r"C:\repo",
            )

    with pytest.raises(McpRetryableError, match=expected):
        service._understand_file_target(  # noqa: SLF001
            _Repo(),
            "src/GameDetailPage.tsx",
            related_test_limit=1,
            detail_level="standard",
            include_reference_sites=True,
            include_implementation_locations=True,
            enable_implementation_flow=True,
            enable_hot_entrypoints=True,
            reference_site_limit=None,
            evidence_tier=CodeEvidenceTier.SEMANTIC,
        )


def test_semantic_runtime_retry_helper_succeeds_after_retry(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    attempts = {"count": 0}

    def _build():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise CoordinatorRuntimeNotReadyError(
                server_family=ServerFamily.GOPLS,
                attachment_root="C:\\repo",
                state=ManagedServerState.WARMING,
                retry_after_seconds=15,
            )
        return "ok"

    result = service._with_semantic_runtime_retries(  # noqa: SLF001
        tool_name="understand_file",
        build_target=_build,
    )

    assert result == "ok"
    assert attempts["count"] == 2


def test_semantic_runtime_retry_helper_retries_three_total_attempts(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    attempts = {"count": 0}

    def _build():
        attempts["count"] += 1
        raise CoordinatorRuntimeNotReadyError(
            server_family=ServerFamily.GOPLS,
            attachment_root="C:\\repo",
            state=ManagedServerState.WARMING,
            retry_after_seconds=15,
        )

    with pytest.raises(McpRetryableError, match="attempted_retries=3 max_attempts=3 retry_exhausted=true"):
        service._with_semantic_runtime_retries(  # noqa: SLF001
            tool_name="understand_file",
            build_target=_build,
        )

    assert attempts["count"] == 3


def test_semantic_runtime_retry_helper_stops_when_sleep_budget_is_exhausted(service: SuitMcpService, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(service, "_SEMANTIC_RUNTIME_MAX_TOTAL_RETRY_SLEEP_SECONDS", 5.0)
    attempts = {"count": 0}

    def _build():
        attempts["count"] += 1
        raise CoordinatorRuntimeNotReadyError(
            server_family=ServerFamily.GOPLS,
            attachment_root="C:\\repo",
            state=ManagedServerState.WARMING,
            retry_after_seconds=15,
        )

    with pytest.raises(McpRetryableError, match="retry_exhausted=true"):
        service._with_semantic_runtime_retries(  # noqa: SLF001
            tool_name="understand_file",
            build_target=_build,
        )

    assert sleeps == [5.0]
    assert attempts["count"] == 2


def test_semantic_runtime_retry_helper_does_not_retry_non_retryable_errors(service: SuitMcpService, monkeypatch) -> None:
    monkeypatch.setattr("suitcode.mcp.service.time.sleep", lambda seconds: None)
    attempts = {"count": 0}

    def _build():
        attempts["count"] += 1
        raise McpValidationError("bad input")

    with pytest.raises(McpValidationError, match="bad input"):
        service._with_semantic_runtime_retries(  # noqa: SLF001
            tool_name="understand_file",
            build_target=_build,
        )

    assert attempts["count"] == 1


def test_full_detail_level_rejects_multi_target_understand_file_requests(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-full-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("A.tsx", "B.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    with pytest.raises(McpValidationError, match="detail_level=full supports exactly 1 target"):
        service.understand_file(
            str(repo_root),
            ("src/A.tsx", "src/B.tsx"),
            detail_level="full",
        )


def test_full_detail_level_rejects_multi_target_change_impact_requests(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-full-impact-grouped"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text('{"name":"frontend","private":true}', encoding="utf-8")
    for name in ("A.tsx", "B.tsx"):
        (repo_root / "src" / name).write_text(
            f"export const {name.removesuffix('.tsx')} = () => null;\n",
            encoding="utf-8",
        )

    with pytest.raises(McpValidationError, match="detail_level=full supports exactly 1 target"):
        service.what_changes_if_i_edit_this(
            str(repo_root),
            ("src/A.tsx", "src/B.tsx"),
            detail_level="full",
        )


def test_explicit_artifact_member_uses_artifact_surface_summary_without_inherited_frontend_proof(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "frontend-artifacts"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "public" / "runtimes").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "main": "public/runtimes/index.js",
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
    (repo_root / "public" / "runtimes" / "bundle.js").write_text("console.log('bundle');\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("public/runtimes/bundle.js",),
    )
    file_understanding = service.understand_file(
        str(repo_root),
        ("public/runtimes/bundle.js",),
        detail_level="compact",
    )
    impact = service.what_changes_if_i_edit_this(
        str(repo_root),
        ("public/runtimes/bundle.js",),
        detail_level="compact",
    )

    assert minimum.compact_summary.required_validation == tuple()
    assert any(
        item.reason_code == "no_deterministic_validation_surface_for_artifact_member"
        for item in minimum.excluded_items
    )
    assert file_understanding.targets[0].artifact_surface_summary is not None
    assert file_understanding.targets[0].artifact_surface_summary.artifact_root == "public/runtimes"
    assert hasattr(file_understanding.targets[0], "frontend_proof_summary") is False
    assert hasattr(file_understanding.targets[0], "implementation_flow_summary") is False
    assert impact.targets[0].artifact_surface_summary is not None
    assert hasattr(impact.targets[0], "frontend_proof_summary") is False
    assert hasattr(impact.targets[0], "implementation_flow_summary") is False


def test_batch_minimum_verified_compact_summary_keeps_one_closest_surface_per_target(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "mixed-surfaces"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "server").mkdir(parents=True)
    (repo_root / "server" / "go.mod").write_text("module example.com/mixed\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "server" / "internal" / "save_sync").mkdir(parents=True)
    (repo_root / "server" / "internal" / "save_sync" / "service.go").write_text(
        "package save_sync\n\nfunc Sync() string { return \"ok\" }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "internal" / "save_sync" / "service_test.go").write_text(
        "package save_sync\n\nimport \"testing\"\n\nfunc TestSync(t *testing.T) { _ = Sync() }\n",
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src").mkdir(parents=True)
    (repo_root / "server" / "frontend" / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "build": "tsc --noEmit && vite build"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "server" / "frontend" / "src" / "App.tsx").write_text(
        "export const App = () => null;\n",
        encoding="utf-8",
    )

    minimum = service.what_should_i_run(
        str(repo_root / "server"),
        repository_rel_paths=("internal/save_sync/service.go", "frontend/src/App.tsx"),
    )

    summaries = tuple(item.summary for item in minimum.compact_summary.required_validation[:2])
    assert any("internal/save_sync" in item for item in summaries)
    assert any("npm run build" in item for item in summaries)


def test_frontend_standalone_package_uses_test_prefixed_script_for_validation(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "test:unit": "vitest run"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")
    (repo_root / "src" / "LibraryPage.spec.jsx").write_text("it('works', () => {});\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/LibraryPage.tsx",),
    )
    availability = service.can_i_do_this(
        str(repo_root),
        repository_rel_path="src/LibraryPage.tsx",
        requested_action_kind="test",
    )

    assert [item.test_id for item in minimum.tests] == ["test:npm:frontend"]
    assert minimum.tests[0].command.argv_preview == ("npm", "run", "test:unit")
    assert not any(item.reason_code == "no_deterministic_test_targets_available" for item in minimum.excluded_items)
    assert availability.supported is True
    assert "test" in availability.available_action_kinds


def test_frontend_standalone_package_prefers_non_watch_test_script(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "scripts": {
            "test:watch": "vitest --watch",
            "test:unit": "vitest run"
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "LibraryPage.tsx").write_text("export const LibraryPage = () => null;\n", encoding="utf-8")
    (repo_root / "src" / "LibraryPage.spec.tsx").write_text("it('works', () => {});\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("src/LibraryPage.tsx",),
    )

    assert [item.test_id for item in minimum.tests] == ["test:npm:frontend"]
    assert minimum.tests[0].command.argv_preview == ("npm", "run", "test:unit")


def test_what_should_i_run_returns_exclusion_for_markdown_only_target(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "docs-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "scan_events.md").write_text("# Scan Events\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("scan_events.md",),
    )
    availability = service.can_i_do_this(
        str(repo_root),
        repository_rel_path="scan_events.md",
        requested_action_kind="test",
    )

    assert minimum.tests == tuple()
    assert minimum.build_targets == tuple()
    assert minimum.compact_summary.required_validation_count == 0
    assert any(
        item.reason_code == "no_deterministic_validation_surfaces_for_provider_owned_artifact"
        for item in minimum.excluded_items
    )
    assert availability.supported is False
    assert availability.reason_code == "actions_truth_unavailable"


def test_what_should_i_run_returns_exclusion_for_openapi_only_target(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "api-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "openapi.yaml").write_text("openapi: 3.1.0\npaths: {}\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("openapi.yaml",),
    )

    assert minimum.tests == tuple()
    assert minimum.build_targets == tuple()
    assert any(
        item.reason_code == "no_deterministic_validation_surfaces_for_provider_owned_artifact"
        for item in minimum.excluded_items
    )


def test_mixed_code_and_docs_targets_include_validations_and_exclusions(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/repo\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "internal" / "http").mkdir(parents=True)
    (repo_root / "internal" / "http" / "server.go").write_text("package http\n\nfunc Value() string { return \"ok\" }\n", encoding="utf-8")
    (repo_root / "internal" / "http" / "server_test.go").write_text("package http\n\nimport \"testing\"\n\nfunc TestValue(t *testing.T) {}\n", encoding="utf-8")
    (repo_root / "scan_events.md").write_text("# Scan Events\n", encoding="utf-8")
    (repo_root / "openapi.yaml").write_text("openapi: 3.1.0\npaths: {}\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("internal/http/server.go", "scan_events.md", "openapi.yaml"),
    )

    assert [item.test_id for item in minimum.tests] == ["test:go:example.com/repo/internal/http"]
    assert any(
        item.reason_code == "no_deterministic_validation_surfaces_for_provider_owned_artifact"
        for item in minimum.excluded_items
    )
    assert not any(item.reason_code == "runner_not_directly_validation_relevant" for item in minimum.excluded_items)
    assert not any(
        item.item_kind == "runner_action"
        for item in minimum.compact_summary.exclusions
    )


def test_docs_only_validation_exclusions_omit_runner_noise_in_mixed_repo(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/repo\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "cmd" / "server").mkdir(parents=True)
    (repo_root / "cmd" / "server" / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    (repo_root / "scan_events.md").write_text("# Scan Events\n", encoding="utf-8")

    minimum = service.what_should_i_run(
        str(repo_root),
        repository_rel_paths=("scan_events.md",),
    )

    assert minimum.tests == tuple()
    assert minimum.build_targets == tuple()
    assert minimum.runner_actions == tuple()
    assert [item.reason_code for item in minimum.excluded_items] == [
        "no_deterministic_validation_surfaces_for_provider_owned_artifact"
    ]


def test_grouped_frontend_file_and_change_tools_do_not_raise_provenance_hash_errors(
    service: SuitMcpService,
    npm_repo_root: Path,
) -> None:
    targets = (
        "apps/admin-portal/src/index.tsx",
        "apps/web-app/src/index.tsx",
        "libs/shared-ui/src/index.tsx",
    )

    understanding_standard = service.understand_file(
        str(npm_repo_root),
        targets,
        detail_level="standard",
    )
    understanding_compact = service.understand_file(
        str(npm_repo_root),
        targets,
        detail_level="compact",
    )
    impact_standard = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        targets,
        detail_level="standard",
    )
    impact_compact = service.what_changes_if_i_edit_this(
        str(npm_repo_root),
        targets,
        detail_level="compact",
    )

    assert understanding_standard.target_count == 3
    assert understanding_compact.target_count == 3
    assert understanding_compact.completed_target_count == 3
    assert impact_standard.target_count == 3
    assert impact_compact.target_count == 3
    assert impact_compact.completed_target_count == 3
    assert all(target.decision_summary for target in understanding_compact.targets)
    assert all(target.decision_summary for target in impact_compact.targets)


def test_hot_entrypoints_preview_prioritizes_externally_referenced_exported_symbols(service: SuitMcpService) -> None:
    class _FakeSymbol:
        def __init__(self, symbol_id: str, name: str, kind: str, line_start: int) -> None:
            self.id = symbol_id
            self.name = name
            self.entity_kind = kind
            self.repository_rel_path = "internal/core/entities.go"
            self.line_start = line_start

    class _FakeLocation:
        def __init__(self, path: str) -> None:
            self.repository_rel_path = path

    class _FakeCode:
        def __init__(self) -> None:
            self._symbols = tuple(
                [_FakeSymbol("entity:entities.go:ExportedHot", "ExportedHot", "function", 10)]
                + [_FakeSymbol("entity:entities.go:localHot", "localHot", "function", 20)]
                + [_FakeSymbol("entity:entities.go:ColdType", "ColdType", "struct", 30)]
                + [_FakeSymbol(f"entity:entities.go:helper{i}", f"helper{i}", "variable", 40 + i) for i in range(17)]
            )
            self._references = {
                "entity:entities.go:ExportedHot": (_FakeLocation("internal/http/routes.go"), _FakeLocation("internal/db/store.go")),
                "entity:entities.go:localHot": (_FakeLocation("internal/core/entities.go"),),
                "entity:entities.go:ColdType": tuple(),
            }

        def list_symbols_in_file(self, repository_rel_path: str):
            return self._symbols

        def find_references_by_symbol_id(self, symbol_id: str):
            return self._references.get(symbol_id, tuple())

    class _FakeRepo:
        def __init__(self) -> None:
            self.code = _FakeCode()

    preview = service._hot_entrypoints_preview(  # type: ignore[attr-defined]
        _FakeRepo(),
        "internal/core/entities.go",
        detail_level="compact",
    )

    assert [item.name for item in preview] == ["ExportedHot", "ColdType", "localHot"]
    assert preview[0].external_reference_count == 2
    assert len(preview) == 3


def test_hot_entrypoints_preview_fails_fast_when_reference_scan_exceeds_budget(
    service: SuitMcpService,
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _FakeSymbol:
        def __init__(self, symbol_id: str, name: str, kind: str, line_start: int) -> None:
            self.id = symbol_id
            self.name = name
            self.entity_kind = kind
            self.repository_rel_path = "src/GameDetailPage.tsx"
            self.line_start = line_start

    class _FakeLocation:
        def __init__(self, path: str) -> None:
            self.repository_rel_path = path

    class _FakeCode:
        def list_symbols_in_file(self, repository_rel_path: str):
            return tuple(
                _FakeSymbol(f"symbol:{index}", f"Component{index}", "function", index + 1)
                for index in range(20)
            )

        def find_references_by_symbol_id(self, symbol_id: str):
            return (_FakeLocation("src/App.tsx"),)

    class _FakeRepo:
        def __init__(self, root: Path) -> None:
            self.root = root
            self.code = _FakeCode()

    timestamps = iter((0.0, 0.0, 9.0, 9.1))
    monkeypatch.setattr("suitcode.mcp.service.time.monotonic", lambda: next(timestamps))

    with pytest.raises(SemanticQueryTimeoutError) as exc_info:
        service._hot_entrypoints_preview(  # type: ignore[attr-defined]
            _FakeRepo(tmp_path),
            "src/GameDetailPage.tsx",
            detail_level="standard",
            deadline=8.0,
        )

    assert exc_info.value.server_name == "typescript-language-server"
    assert exc_info.value.attachment_root == str(tmp_path)
    assert exc_info.value.retry_after_seconds == 15


def test_what_changes_if_i_edit_this_supports_provider_owned_markdown_and_openapi(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "docs-repo"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "scan_events.md").write_text("# Scan Events\n", encoding="utf-8")
    (repo_root / "openapi.yaml").write_text("openapi: 3.1.0\npaths: {}\n", encoding="utf-8")

    impact = service.what_changes_if_i_edit_this(
        str(repo_root),
        ("scan_events.md", "openapi.yaml"),
    )

    assert impact.target_count == 2
    assert {item.owner.id for item in impact.targets} == {
        "component:markdown:documents",
        "component:openapi:specs",
    }


def test_repository_summary_excludes_tracked_artifact_files_from_file_count(
    service: SuitMcpService,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "frontend"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "dist").mkdir(parents=True)
    (repo_root / "package.json").write_text(
        """
        {
          "name": "frontend",
          "private": true,
          "main": "dist/index.js"
        }
        """.strip(),
        encoding="utf-8",
    )
    (repo_root / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    (repo_root / "dist" / "index.js").write_text("export const value = 1;\n", encoding="utf-8")

    monkeypatch.setattr(service, "_wait_for_repository_warmup", lambda repository: None)
    understanding = service.understand_repository(str(repo_root), preview_limit=10)

    assert understanding.repository.file_count == 2
    ownership_provenance = next(
        item for item in understanding.repository.provenance if item.source_kind == "ownership"
    )
    assert "dist/index.js" not in ownership_provenance.evidence_paths


def test_read_only_by_path_minimum_verified_change_set_returns_clear_empty_surface_error(
    service: SuitMcpService,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "go-orphan"
    (repo_root / ".git").mkdir(parents=True)
    (repo_root / "go.mod").write_text("module example.com/orphan\n\ngo 1.22\n", encoding="utf-8")
    (repo_root / "pkg" / "orphan").mkdir(parents=True)
    (repo_root / "pkg" / "orphan" / "orphan.go").write_text(
        'package orphan\n\nfunc Value() string { return "orphan" }\n',
        encoding="utf-8",
    )

    with pytest.raises(
        McpValidationError,
        match=r"no deterministic validation surfaces were found for file target `pkg/orphan/orphan\.go`",
    ):
        service.get_minimum_verified_change_set_by_path(
            str(repo_root),
            repository_rel_path="pkg/orphan/orphan.go",
        )


def test_what_should_i_run_explains_shared_file_validation_breadth(service: SuitMcpService, go_repo_root: Path) -> None:
    minimum = service.what_should_i_run(
        str(go_repo_root),
        ("pkg/util/util.go",),
    )

    assert any(
        item.reason_code == "no_narrower_direct_validation_surface_for_file_target"
        and "dependent-package surfaces required because the file is shared" in item.reason
        for item in minimum.excluded_items
    )
    assert any(
        "dependent-package surfaces required because the file is shared" in item.summary
        for item in minimum.compact_summary.exclusions
    )


def test_service_open_workspace_reuses_same_root(service: SuitMcpService, npm_repo_root: Path) -> None:
    first = service.open_workspace(str(npm_repo_root))
    second = service.open_workspace(str(npm_repo_root))

    assert first.workspace.workspace_id == second.workspace.workspace_id
    assert second.reused is True


def test_service_inspect_repository_support_for_unsupported_repo(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    support = service.inspect_repository_support(str(repo_root))

    assert support.is_supported is False


def test_service_open_workspace_fails_for_unsupported_repo(service: SuitMcpService, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    with pytest.raises(McpUnsupportedRepositoryError):
        service.open_workspace(str(repo_root))


def test_service_list_components_and_tests(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    components = service.list_components(workspace_id, repository_id, limit=10, offset=0)
    tests = service.list_tests(workspace_id, repository_id, limit=10, offset=0)

    assert components.total >= 1
    assert components.items[0].provenance
    assert tests.total >= 1
    assert hasattr(tests.items[0], "provenance")
    assert tests.items[0].provenance


def test_service_list_actions_and_filters(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    all_actions = service.list_actions(workspace_id, repository_id, limit=200, offset=0)
    assert all_actions.total >= 1
    assert all(item.provenance for item in all_actions.items)
    assert any(item.kind == "runner_execution" for item in all_actions.items)
    assert any(item.kind == "test_execution" for item in all_actions.items)

    runner_target = next(item.target_id for item in all_actions.items if item.target_kind == "runner")
    runner_actions = service.list_actions(
        workspace_id,
        repository_id,
        runner_id=runner_target,
        limit=200,
        offset=0,
    )
    assert runner_actions.total >= 1
    assert all(item.target_id == runner_target for item in runner_actions.items)

    test_actions = service.list_actions(
        workspace_id,
        repository_id,
        action_kinds=("test_execution",),
        limit=200,
        offset=0,
    )
    assert test_actions.total >= 1
    assert all(item.kind == "test_execution" for item in test_actions.items)


def test_service_lists_and_executes_build_targets(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)

    targets = service.list_build_targets(workspace_id, repository_id, limit=200, offset=0)
    assert targets.total >= 1
    assert targets.items[0].provenance
    action_id = targets.items[0].action_id

    described = service.describe_build_target(workspace_id, repository_id, action_id=action_id)
    assert described.action_id == action_id
    assert described.provenance

    class _FakeActionExecutionService:
        def run(
            self,
            *,
            action_id: str,
            command_argv: tuple[str, ...],
            command_cwd: str | None,
            timeout_seconds: int,
            run_group: str,
        ) -> ActionExecutionResult:
            return ActionExecutionResult(
                action_id=action_id,
                status=ActionExecutionStatus.PASSED,
                success=True,
                command_argv=command_argv,
                command_cwd=command_cwd,
                exit_code=0,
                duration_ms=timeout_seconds,
                log_path=".suit/runs/builds/fake.log",
                output_excerpt="ok",
                output="ok",
            )

    repository._build_service = BuildService(  # type: ignore[attr-defined]
        repository,
        action_execution_service=_FakeActionExecutionService(),
    )

    target_result = service.build_target(
        workspace_id,
        repository_id,
        action_id=action_id,
        timeout_seconds=33,
    )
    assert target_result.action_id == action_id
    assert target_result.status == "passed"
    assert target_result.duration_ms == 33
    assert target_result.provenance

    project_result = service.build_project(
        workspace_id,
        repository_id,
        timeout_seconds=33,
    )
    assert project_result.total == targets.total
    assert project_result.passed == targets.total
    assert project_result.failed == 0
    assert project_result.errors == 0
    assert project_result.timeouts == 0
    assert project_result.failed_results == tuple()
    assert project_result.provenance


def test_service_build_methods_fail_fast_for_unknown_action(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_build_target(workspace_id, repository_id, action_id="action:missing")

    with pytest.raises(McpValidationError):
        service.build_target(workspace_id, repository_id, action_id="action:missing")


def test_service_list_actions_validates_query(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.list_actions(
            workspace_id,
            repository_id,
            owner_id="component:npm:@monorepo/core",
            component_id="component:npm:@monorepo/core",
        )

    with pytest.raises(McpValidationError):
        service.list_actions(
            workspace_id,
            repository_id,
            action_kinds=("unsupported",),
        )


def test_service_find_symbols_requires_valid_query(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.find_symbols(workspace_id, repository_id, query="   ")


def test_service_find_symbols_passes_case_sensitive_flag(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False):
            if is_case_sensitive and query == "core":
                return tuple()
            return (
                type("FakeSymbol", (), {
                    "name": "Core",
                    "kind": "class",
                    "repository_rel_path": "packages/core/src/index.ts",
                    "line_start": 1,
                    "line_end": 11,
                    "column_start": 1,
                    "column_end": 2,
                    "container_name": None,
                    "signature": None,
                })(),
            )

    provider._symbol_service = _FakeSymbolService()  # type: ignore[attr-defined]

    insensitive = service.find_symbols(workspace_id, repository_id, query="core", limit=50, offset=0)
    sensitive = service.find_symbols(
        workspace_id,
        repository_id,
        query="core",
        is_case_sensitive=True,
        limit=50,
        offset=0,
    )

    assert insensitive.total >= 1
    assert insensitive.items[0].provenance
    assert sensitive.total == 0


def test_service_find_symbols_returns_enriched_symbol_context(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    from suitcode.core.models.nodes import TestDefinition, TestFramework
    from suitcode.core.provenance_builders import test_tool_provenance
    from suitcode.core.tests.models import DiscoveredTestDefinition, RelatedTestMatch, ResolvedRelatedTest
    from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol

    class _FakeSymbolService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False):
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=13,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="class Core",
                ),
            )

    class _FakeFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                NpmWorkspaceSymbol(
                    name="Core",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=1,
                    line_end=13,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature="class Core",
                ),
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (
                ("packages/core/src/index.ts", 1, 13, 1, 2),
                ("packages/utils/src/index.ts", 7, 9, 1, 2),
            )

    provider._symbol_service = _FakeSymbolService()  # type: ignore[attr-defined]
    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]
    test_definition = TestDefinition(
        id="test:npm:@monorepo/core",
        name="@monorepo/core tests",
        framework=TestFramework.OTHER,
        test_files=("packages/core/src/index.test.ts",),
        provenance=(
            test_tool_provenance(
                source_tool="jest",
                evidence_summary="authoritative jest discovery for core tests",
                evidence_paths=("packages/core/src/index.test.ts",),
            ),
        ),
    )
    test_provenance = (
        test_tool_provenance(
            source_tool="jest",
            evidence_summary="authoritative jest discovery for core tests",
            evidence_paths=("packages/core/src/index.test.ts",),
        ),
    )
    repository.tests.get_related_tests = lambda target: (  # type: ignore[method-assign]
        ResolvedRelatedTest(
            match=RelatedTestMatch(
                test_definition=test_definition,
                relation_reason="same_component",
                matched_owner_id="component:npm:@monorepo/core",
                matched_repository_rel_path="packages/core/src/index.ts",
            ),
            discovered_test=DiscoveredTestDefinition(
                test_definition=test_definition,
                provenance=test_provenance,
            ),
        ),
    )

    result = service.find_symbols(workspace_id, repository_id, query="Core")

    assert result.total == 1
    hit = result.items[0]
    assert hit.owner is not None
    assert hit.owner.id == "component:npm:@monorepo/core"
    assert hit.reference_count == 1
    assert len(hit.reference_preview) == 1
    assert hit.reference_preview[0].path == "packages/utils/src/index.ts"
    assert hit.definition_anchor is not None
    assert hit.definition_anchor.path == "packages/core/src/index.ts"
    assert hit.related_tests_preview
    assert hit.context_source == "symbol + owner + references + related_tests"


def test_service_find_symbols_defaults_to_compact_top_level_budget(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    from suitcode.providers.npm.symbol_models import NpmWorkspaceSymbol

    class _ManySymbolsService:
        def get_symbols(self, query: str, is_case_sensitive: bool = False):
            return tuple(
                NpmWorkspaceSymbol(
                    name=f"Core{i}",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=i + 1,
                    line_end=i + 1,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature=None,
                )
                for i in range(6)
            )

    class _SparseFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return tuple(
                NpmWorkspaceSymbol(
                    name=f"Core{i}",
                    kind="class",
                    repository_rel_path="packages/core/src/index.ts",
                    line_start=i + 1,
                    line_end=i + 1,
                    column_start=1,
                    column_end=2,
                    container_name=None,
                    signature=None,
                )
                for i in range(6)
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", line, line, column, column + 1),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (("packages/core/src/index.ts", line, line, column, column + 1),)

    provider._symbol_service = _ManySymbolsService()  # type: ignore[attr-defined]
    provider._file_symbol_service = _SparseFileSymbolService()  # type: ignore[attr-defined]

    result = service.find_symbols(workspace_id, repository_id, query="Core*")

    assert result.limit == 5
    assert result.total == 6
    assert len(result.items) == 5
    assert result.truncated is True


def test_service_quality_requires_provider_id(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.format_file(workspace_id, repository_id, "packages/core/src/index.ts", provider_id="missing")


def test_service_quality_results_include_provenance(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeQualityService:
        def lint_file(self, repository_rel_path: str, is_fix: bool):
            from suitcode.core.provenance_builders import lsp_delta_provenance, quality_tool_provenance
            from suitcode.providers.quality_models import QualityDiagnostic, QualityEntityDelta, QualityFileResult

            return QualityFileResult(
                repository_rel_path=repository_rel_path,
                tool="eslint",
                operation="lint",
                changed=False,
                success=True,
                message=None,
                diagnostics=(
                    QualityDiagnostic(
                        tool="eslint",
                        severity="warning",
                        message="issue",
                        provenance=(
                            quality_tool_provenance(
                                source_tool="eslint",
                                evidence_summary="eslint diagnostic",
                                evidence_paths=(repository_rel_path,),
                            ),
                        ),
                    ),
                ),
                entity_delta=QualityEntityDelta(
                    provenance=(
                        lsp_delta_provenance(
                            source_tool="typescript-language-server",
                            evidence_summary="delta from lsp",
                            evidence_paths=(repository_rel_path,),
                        ),
                    ),
                ),
                applied_fixes=is_fix,
                content_sha_before="before",
                content_sha_after="before",
                provenance=(
                    quality_tool_provenance(
                        source_tool="eslint",
                        evidence_summary="eslint result",
                        evidence_paths=(repository_rel_path,),
                    ),
                    lsp_delta_provenance(
                        source_tool="typescript-language-server",
                        evidence_summary="result includes lsp delta",
                        evidence_paths=(repository_rel_path,),
                    ),
                ),
            )

    provider._quality_service = _FakeQualityService()  # type: ignore[attr-defined]

    result = service.lint_file(
        workspace_id,
        repository_id,
        "packages/core/src/index.ts",
        provider_id="npm",
        is_fix=False,
    )

    assert result.provenance
    assert result.diagnostics[0].provenance
    assert result.entity_delta.provenance


def test_service_close_workspace_invalidates_lookup(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id

    service.close_workspace(workspace_id)

    with pytest.raises(McpNotFoundError):
        service.get_workspace(workspace_id)


def test_service_pagination_enforces_limit(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.list_components(workspace_id, repository_id, limit=201, offset=0)


def test_service_exposes_owner_related_test_and_summary_tools(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    file_owner = service.get_file_owner(workspace_id, repository_id, "packages/core/src/index.ts")
    owned_files = service.list_files_by_owner(
        workspace_id,
        repository_id,
        owner_id="component:npm:@monorepo/core",
        limit=50,
        offset=0,
    )
    related_tests = service.get_related_tests(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
        limit=50,
        offset=0,
    )
    summary = service.repository_summary(workspace_id, repository_id, preview_limit=5)

    assert file_owner.owner.id == "component:npm:@monorepo/core"
    assert owned_files.total >= 1
    assert any(item.id == "test:npm:@monorepo/core" for item in related_tests.items)
    assert all(item.provenance for item in related_tests.items)
    assert summary.repository_id == repository_id
    assert summary.preview_limit == 5
    assert summary.component_count >= 1
    assert summary.truth_coverage is None
    assert summary.provenance
    assert any(item.source_kind == "test_tool" for item in summary.provenance)


def test_service_describe_and_run_test_targets(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    description = service.describe_test_target(
        workspace_id,
        repository_id,
        test_id="test:npm:@monorepo/core",
    )
    assert description.id == "test:npm:@monorepo/core"
    assert description.command_argv
    assert description.provenance

    class _FakeExecutionService:
        def run_target(self, target_description, timeout_seconds: int):
            from suitcode.core.provenance_builders import heuristic_provenance
            from suitcode.core.tests.models import TestExecutionResult, TestExecutionStatus

            return TestExecutionResult(
                test_id=target_description.test_definition.id,
                status=TestExecutionStatus.PASSED,
                success=True,
                command_argv=target_description.command_argv,
                command_cwd=target_description.command_cwd,
                exit_code=0,
                duration_ms=timeout_seconds,
                log_path=".suit/runs/tests/fake.log",
                warning=target_description.warning,
                output_excerpt="ok",
                provenance=(
                    heuristic_provenance(
                        evidence_summary="fake execution result",
                        evidence_paths=("packages/core/src/index.test.ts",),
                    ),
                ),
            )

    provider._test_execution_service = _FakeExecutionService()  # type: ignore[attr-defined]
    run_result = service.run_test_targets(
        workspace_id,
        repository_id,
        test_ids=("test:npm:@monorepo/core",),
        timeout_seconds=25,
    )

    assert run_result.total == 1
    assert run_result.passed == 1
    assert run_result.results[0].test_id == "test:npm:@monorepo/core"
    assert run_result.results[0].duration_ms == 25


def test_service_describe_and_run_runner(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)

    runners = service.list_runners(workspace_id, repository_id, limit=10, offset=0)
    assert runners.total >= 1
    runner_id = runners.items[0].id

    context = service.describe_runner(workspace_id, repository_id, runner_id=runner_id)
    assert context.runner.id == runner_id
    assert context.action_id
    assert context.provenance

    class _FakeActionExecutionService:
        def run(
            self,
            *,
            action_id: str,
            command_argv: tuple[str, ...],
            command_cwd: str | None,
            timeout_seconds: int,
            run_group: str,
        ) -> ActionExecutionResult:
            return ActionExecutionResult(
                action_id=action_id,
                status=ActionExecutionStatus.PASSED,
                success=True,
                command_argv=command_argv,
                command_cwd=command_cwd,
                exit_code=0,
                duration_ms=timeout_seconds,
                log_path=".suit/runs/runners/fake.log",
                output_excerpt="ok",
                output="ok",
            )

    repository._runner_service = RunnerService(  # type: ignore[attr-defined]
        repository,
        action_execution_service=_FakeActionExecutionService(),
    )
    run_result = service.run_runner(
        workspace_id,
        repository_id,
        runner_id=runner_id,
        timeout_seconds=21,
    )

    assert run_result.runner_id == runner_id
    assert run_result.status == "passed"
    assert run_result.duration_ms == 21


def test_service_runner_methods_fail_fast_for_unknown_runner(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_runner(workspace_id, repository_id, runner_id="runner:missing")

    with pytest.raises(McpValidationError):
        service.run_runner(workspace_id, repository_id, runner_id="runner:missing")


def test_service_exposes_component_file_and_impact_context(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository = service._registry.get_repository(workspace_id, repository_id)
    provider = repository.get_provider("npm")

    class _FakeFileSymbolService:
        def list_file_symbols(self, repository_rel_path: str, query: str | None = None, is_case_sensitive: bool = False):
            return (
                type(
                    "FakeSymbol",
                    (),
                    {
                        "name": "Core",
                        "kind": "class",
                        "repository_rel_path": "packages/core/src/index.ts",
                        "line_start": 1,
                        "line_end": 13,
                        "column_start": 1,
                        "column_end": 2,
                        "container_name": None,
                        "signature": "class Core",
                    },
                )(),
            )

        def find_definition(self, repository_rel_path: str, line: int, column: int):
            return (("packages/core/src/index.ts", 1, 13, 1, 2),)

        def find_references(self, repository_rel_path: str, line: int, column: int, include_definition: bool = False):
            return (
                ("packages/core/src/index.ts", 1, 13, 1, 2),
                ("packages/utils/src/index.ts", 7, 9, 1, 2),
            )

    class _FakeRelationshipService:
        def get_file_relationships(self, repository_rel_path: str) -> tuple[FileRelationshipRef, ...]:
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                FileRelationshipRef(
                    repository_rel_path="packages/utils/src/index.ts",
                    relationship_kind=FileRelationshipKind.IMPORTED_BY,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved import edge",
                            evidence_paths=("packages/core/src/index.ts", "packages/utils/src/index.ts"),
                        ),
                    ),
                ),
            )

    class _FakeRenderEdgeService:
        def get_file_render_edges(self, repository_rel_path: str) -> tuple[RenderEdgeRef, ...]:
            assert repository_rel_path == "packages/core/src/index.ts"
            return (
                RenderEdgeRef(
                    repository_rel_path="packages/ui/src/Button.tsx",
                    relationship_kind=RenderEdgeKind.RENDERS,
                    line_start=12,
                    column_start=5,
                    prop_names=("label", "variant"),
                    has_spread_props=False,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="resolved JSX render edge",
                            evidence_paths=("packages/core/src/index.ts", "packages/ui/src/Button.tsx"),
                        ),
                    ),
                ),
            )

    class _FakeStaticAnalysisService:
        def get_file_analysis(self, repository_rel_path: str):
            assert repository_rel_path == "packages/core/src/index.ts"
            findings = (
                InvariantFindingRef(
                    repository_rel_path="packages/core/src/index.ts",
                    finding_kind=InvariantFindingKind.MAYBE_MISSING_FIELD_ACCESS,
                    access_kind=InvariantAccessKind.METHOD_CALL,
                    line_start=14,
                    column_start=9,
                    field_name="status",
                    subject_label="integration",
                    declared_type="string | undefined",
                    producer_site_count=0,
                    producer_sites_preview=tuple(),
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found maybe-missing field access",
                            evidence_paths=("packages/core/src/index.ts",),
                        ),
                    ),
                ),
            )
            flows = (
                StaticFlowEdgeRef(
                    repository_rel_path="packages/core/src/index.ts",
                    edge_kind=StaticFlowEdgeKind.PRODUCES_VALUE_FOR,
                    line_start=18,
                    column_start=5,
                    source_label="toStateMap",
                    target_label="setState",
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary="deterministic TS analysis found local flow edge",
                            evidence_paths=("packages/core/src/index.ts",),
                        ),
                    ),
                ),
            )
            return findings, flows

    provider._file_symbol_service = _FakeFileSymbolService()  # type: ignore[attr-defined]
    provider._file_relationship_service = _FakeRelationshipService()  # type: ignore[attr-defined]
    provider._render_edge_service = _FakeRenderEdgeService()  # type: ignore[attr-defined]
    provider._static_analysis_service = _FakeStaticAnalysisService()  # type: ignore[attr-defined]

    component_contexts = service.describe_components(
        workspace_id,
        repository_id,
        component_ids=("component:npm:@monorepo/core",),
    )
    file_contexts = service.describe_files(
        workspace_id,
        repository_id,
        repository_rel_paths=("packages/core/src/index.ts",),
    )
    symbol_context = service.describe_symbol_context(
        workspace_id,
        repository_id,
        symbol_id="entity:packages/core/src/index.ts:class:Core:1-13",
    )
    dependencies = service.get_component_dependencies(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/utils",
        limit=50,
        offset=0,
    )
    dependency_edges = service.list_component_dependency_edges(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/utils",
        limit=50,
        offset=0,
    )
    dependents = service.get_component_dependents(
        workspace_id,
        repository_id,
        component_id="component:npm:@monorepo/core",
        limit=50,
        offset=0,
    )
    impact = service.analyze_impact(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )
    change = service.analyze_change(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert component_contexts[0].component.id == "component:npm:@monorepo/core"
    assert component_contexts[0].component.provenance
    assert file_contexts[0].owner.id == "component:npm:@monorepo/core"
    assert file_contexts[0].dependency_file_count == 0
    assert [item.path for item in file_contexts[0].dependent_files_preview] == ["packages/utils/src/index.ts"]
    assert [item.path for item in file_contexts[0].render_children_preview] == ["packages/ui/src/Button.tsx"]
    assert file_contexts[0].render_children_preview[0].prop_names == ("label", "variant")
    assert [item.field_name for item in file_contexts[0].invariant_findings_preview] == ["status"]
    assert [item.target_label for item in file_contexts[0].local_flow_edges_preview] == ["setState"]
    assert file_contexts[0].file.provenance
    assert symbol_context.symbol.name == "Core"
    assert symbol_context.symbol.provenance
    assert symbol_context.definitions[0].provenance
    assert impact.references_preview[0].provenance
    assert any(item.target_id == "component:npm:@monorepo/core" for item in dependencies.items)
    assert all(item.source_component_id == "component:npm:@monorepo/utils" for item in dependency_edges.items)
    assert {item.target_id for item in dependency_edges.items} == {item.target_id for item in dependencies.items}
    assert "component:npm:@monorepo/utils" in dependents.items
    assert impact.target_kind == "file"
    assert change.target_kind == "file"
    assert change.primary_component is not None
    assert change.primary_component.id == "component:npm:@monorepo/core"
    assert [item.path for item in change.dependent_files] == ["packages/utils/src/index.ts"]
    assert [item.path for item in change.render_children] == ["packages/ui/src/Button.tsx"]
    assert change.render_children[0].prop_names == ("label", "variant")
    assert [item.field_name for item in change.invariant_findings] == ["status"]
    assert [item.target_label for item in change.local_flow_edges] == ["setState"]
    assert change.reference_locations
    assert change.related_tests
    assert isinstance(change.related_runners, tuple)
    if change.related_runners:
        assert change.related_runners[0].provenance
    assert change.quality_gates
    assert change.evidence.total_edges >= 1
    assert change.evidence.counts_by_kind["target_owner"] == 1
    assert change.evidence.edges_preview[0].provenance
    assert change.truth_coverage.scope_kind == "change"
    assert change.provenance


def test_service_get_truth_coverage(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    truth = service.get_truth_coverage(workspace_id, repository_id)

    assert truth.scope_kind == "repository"
    assert truth.scope_id == repository_id
    assert {item.domain for item in truth.domains} == {
        "architecture",
        "code",
        "tests",
        "quality",
        "actions",
    }
    assert truth.provenance


def test_service_gets_minimum_verified_change_set(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    change_set = service.get_minimum_verified_change_set(
        workspace_id,
        repository_id,
        repository_rel_path="packages/core/src/index.ts",
    )

    assert change_set.compact_summary.required_validation_count >= 1
    assert change_set.compact_summary.required_validation[0].summary
    assert change_set.target_kind == "file"
    assert change_set.owner.id == "component:npm:@monorepo/core"
    assert [item.test_id for item in change_set.tests] == ["test:npm:@monorepo/core"]
    assert change_set.tests[0].command.total_arg_count >= 1
    assert change_set.quality_validation_operations[0].repository_rel_paths == ("packages/core/src/index.ts",)
    assert change_set.quality_validation_operations[0].proof_edges[0].provenance
    assert change_set.provenance


def test_service_list_component_dependency_edges_fails_for_unknown_component(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpNotFoundError):
        service.list_component_dependency_edges(
            workspace_id,
            repository_id,
            component_id="component:npm:missing",
        )


def test_service_exact_batch_and_preview_validation_fail_fast(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id

    with pytest.raises(McpValidationError):
        service.describe_components(
            workspace_id,
            repository_id,
            component_ids=("component:npm:@monorepo/core", "component:npm:@monorepo/core"),
        )

    with pytest.raises(McpValidationError):
        service.describe_files(
            workspace_id,
            repository_id,
            repository_rel_paths=tuple(),
        )

    with pytest.raises(McpValidationError):
        service.analyze_change(
            workspace_id,
            repository_id,
            symbol_id="entity:packages/core/src/index.ts:class:Core:1-13",
            repository_rel_path="packages/core/src/index.ts",
        )

    with pytest.raises(McpValidationError):
        service.analyze_change(
            workspace_id,
            repository_id,
            repository_rel_path="packages/core/src/index.ts",
            runner_preview_limit=0,
        )


def test_service_analytics_views_return_structured_data(service: SuitMcpService, opened_workspace) -> None:
    workspace_id = opened_workspace.workspace.workspace_id
    repository_id = opened_workspace.initial_repository.repository_id
    repository_root = service._registry.get_repository(workspace_id, repository_id).root

    service.analytics_recorder.record_success(
        tool_name="list_supported_providers",
        arguments={},
        repository_root=None,
        result={"items": [{"provider_id": "python"}]},
        duration_ms=7,
    )
    service.analytics_recorder.record_success(
        tool_name="list_components",
        arguments={"workspace_id": workspace_id, "repository_id": repository_id, "limit": 10, "offset": 0},
        repository_root=repository_root,
        result={"items": [{"id": "component:npm:@monorepo/core"}]},
        duration_ms=9,
    )

    summary_repo_local = service.get_analytics_summary(
        workspace_id=workspace_id,
        repository_id=repository_id,
    )
    summary_with_global = service.get_analytics_summary(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
    )
    session_id = service.analytics_recorder._session_id  # type: ignore[attr-defined]
    usage = service.get_tool_usage_analytics(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
        session_id=session_id,
        limit=50,
        offset=0,
    )
    ineff = service.get_inefficient_tool_calls(
        workspace_id=workspace_id,
        repository_id=repository_id,
        include_global=True,
        session_id=session_id,
        limit=50,
        offset=0,
    )

    assert summary_repo_local.total_calls >= 1
    assert summary_with_global.total_calls >= summary_repo_local.total_calls
    assert summary_repo_local.estimated_tokens >= 1
    assert usage.total >= 1
    assert isinstance(ineff.items, tuple)
    if ineff.items:
        assert ineff.items[0].session_id == session_id


def test_service_benchmark_report_fails_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUITCODE_ANALYTICS_GLOBAL_ROOT", str(tmp_path / "analytics"))
    service = SuitMcpService(registry=WorkspaceRegistry())
    with pytest.raises(McpNotFoundError):
        service.get_mcp_benchmark_report()
