from __future__ import annotations

from suitcode.core.workspace import Workspace
from suitcode.mcp.presenters import ProviderPresenter, RepositoryPresenter, WorkspacePresenter
from suitcode.providers.npm import NPMProvider


def test_provider_presenter_maps_descriptor() -> None:
    descriptor = NPMProvider.descriptor()
    view = ProviderPresenter().descriptor_view(descriptor)

    assert view.provider_id == "npm"
    assert "architecture" in view.supported_roles


def test_workspace_and_repository_presenters_map_core_objects(npm_repo_root) -> None:
    workspace = Workspace(npm_repo_root)
    repository = workspace.repositories[0]
    workspace_view = WorkspacePresenter().workspace_view(workspace)
    repository_view = RepositoryPresenter().repository_view(repository)

    assert workspace_view.workspace_id.startswith("workspace:")
    assert repository_view.repository_id.startswith("repo:")
    assert repository_view.provider_ids == ("npm",)
