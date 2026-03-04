from pathlib import Path
from typing import TYPE_CHECKING

from suitcode.core.repository import Repository
from suitcode.providers.provider_metadata import ProviderDescriptor
from suitcode.providers.registry import get_provider_descriptors

if TYPE_CHECKING:
    pass


type WorkspaceHandle = str


class Workspace:
    @classmethod
    def supported_providers(cls) -> tuple[ProviderDescriptor, ...]:
        return get_provider_descriptors()

    def __init__(self, repository_directory: Path) -> None:
        initial_root = Repository.root_candidate(repository_directory)
        support = Repository.support_for_path(initial_root)
        if not support.is_supported:
            available = ", ".join(descriptor.provider_id for descriptor in self.supported_providers())
            raise ValueError(
                f"workspace cannot be created for unsupported repository `{initial_root}`. "
                f"No registered providers matched this repository. "
                f"Available providers: {available}."
            )

        self._id = f"workspace:{initial_root.name}"
        self._repositories_by_root: dict[Path, Repository] = {}
        self.add_repository(repository_directory)

    @property
    def id(self) -> str:
        return self._id

    def _next_repository_id(self, repository_root: Path) -> str:
        base_name = repository_root.name
        existing = {repository.id for repository in self._repositories_by_root.values()}
        candidate = f"repo:{base_name}"
        if candidate not in existing:
            return candidate

        suffix = 2
        while True:
            candidate = f"repo:{base_name}-{suffix}"
            if candidate not in existing:
                return candidate
            suffix += 1

    def add_repository(self, repository_directory: Path) -> "Repository":
        repository_root = Repository.root_candidate(repository_directory)
        support = Repository.support_for_path(repository_root)
        if not support.is_supported:
            raise ValueError(f"workspace cannot add unsupported repository `{repository_root}`")
        if repository_root not in self._repositories_by_root:
            repository_id = self._next_repository_id(repository_root)
            self._repositories_by_root[repository_root] = Repository(
                workspace=self,
                repository_directory=repository_root,
                repository_id=repository_id,
            )
        return self._repositories_by_root[repository_root]

    def get_repository(self, repository_directory: Path) -> "Repository":
        return self.add_repository(repository_directory)

    def get_repository_by_id(self, repository_id: str) -> "Repository":
        for repository in self._repositories_by_root.values():
            if repository.id == repository_id:
                return repository
        raise ValueError(f"unknown repository id in workspace `{self._id}`: `{repository_id}`")

    def suit_dir_for(self, repository_directory: Path) -> Path:
        return self.get_repository(repository_directory).suit_dir

    @property
    def repository_roots(self) -> tuple[Path, ...]:
        return tuple(self._repositories_by_root.keys())

    @property
    def repositories(self) -> tuple["Repository", ...]:
        return tuple(self._repositories_by_root.values())

