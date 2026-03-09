from __future__ import annotations

from suitcode.core.repository import Repository
from suitcode.core.repository_models import FileOwnerInfo, OwnedNodeInfo
from suitcode.core.workspace import Workspace
from suitcode.mcp.models import (
    AddRepositoryResult,
    DetectedProviderView,
    FileOwnerView,
    OpenWorkspaceResult,
    OwnerView,
    ProviderDescriptorView,
    RepositorySnapshotView,
    RepositorySupportView,
    RepositoryView,
    WorkspaceSnapshotView,
    WorkspaceView,
)
from suitcode.providers.provider_metadata import DetectedProviderSupport, ProviderDescriptor, RepositorySupportResult

from suitcode.mcp.presenter_common import sorted_role_values


class ProviderPresenter:
    def descriptor_view(self, descriptor: ProviderDescriptor) -> ProviderDescriptorView:
        return ProviderDescriptorView(
            provider_id=descriptor.provider_id,
            display_name=descriptor.display_name,
            build_systems=descriptor.build_systems,
            programming_languages=descriptor.programming_languages,
            supported_roles=sorted_role_values(descriptor.supported_roles),
        )

    def detected_view(self, detected: DetectedProviderSupport) -> DetectedProviderView:
        descriptor = detected.descriptor
        return DetectedProviderView(
            provider_id=descriptor.provider_id,
            display_name=descriptor.display_name,
            detected_roles=sorted_role_values(detected.detected_roles),
            build_systems=descriptor.build_systems,
            programming_languages=descriptor.programming_languages,
        )

    def support_view(self, support: RepositorySupportResult) -> RepositorySupportView:
        return RepositorySupportView(
            repository_root=str(support.repository_root),
            is_supported=support.is_supported,
            detected_providers=tuple(self.detected_view(item) for item in support.detected_providers),
        )


class RepositoryPresenter:
    def repository_view(self, repository: Repository) -> RepositoryView:
        return RepositoryView(
            workspace_id=repository.workspace.id,
            repository_id=repository.id,
            root_path=str(repository.root),
            suit_dir=str(repository.suit_dir),
            provider_ids=repository.provider_ids,
            provider_roles={
                provider_id: sorted_role_values(roles)
                for provider_id, roles in repository.provider_roles.items()
            },
        )

    def repository_snapshot(self, repository: Repository) -> RepositorySnapshotView:
        return RepositorySnapshotView(**self.repository_view(repository).model_dump())


class WorkspacePresenter:
    def __init__(self) -> None:
        self._repository_presenter = RepositoryPresenter()

    def workspace_view(self, workspace: Workspace) -> WorkspaceView:
        repository_ids = tuple(repository.id for repository in workspace.repositories)
        return WorkspaceView(
            workspace_id=workspace.id,
            repository_ids=repository_ids,
            repository_count=len(repository_ids),
        )

    def workspace_snapshot(self, workspace: Workspace) -> WorkspaceSnapshotView:
        repository_ids = tuple(repository.id for repository in workspace.repositories)
        return WorkspaceSnapshotView(
            workspace_id=workspace.id,
            repository_count=len(repository_ids),
            repository_ids=repository_ids,
        )

    def open_workspace_result(self, workspace: Workspace, repository: Repository, reused: bool) -> OpenWorkspaceResult:
        return OpenWorkspaceResult(
            workspace=self.workspace_view(workspace),
            initial_repository=self._repository_presenter.repository_view(repository),
            reused=reused,
        )

    def add_repository_result(
        self,
        workspace_id: str,
        owning_workspace_id: str,
        repository: Repository,
        reused: bool,
    ) -> AddRepositoryResult:
        return AddRepositoryResult(
            workspace_id=workspace_id,
            repository=self._repository_presenter.repository_view(repository),
            owning_workspace_id=owning_workspace_id,
            reused=reused,
        )


class OwnershipPresenter:
    def __init__(self, architecture_presenter=None) -> None:
        if architecture_presenter is None:
            from suitcode.mcp.presenter_architecture import ArchitecturePresenter

            architecture_presenter = ArchitecturePresenter()
        self._architecture_presenter = architecture_presenter

    def owner_view(self, owner: OwnedNodeInfo) -> OwnerView:
        return OwnerView(id=owner.id, kind=owner.kind, name=owner.name)

    def file_owner_view(self, file_owner: FileOwnerInfo) -> FileOwnerView:
        file_view = self._architecture_presenter.file_view(file_owner.file_info)
        return FileOwnerView(file=file_view, owner=self.owner_view(file_owner.owner))
