from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
    from suitcode.core.code.code_intelligence import CodeIntelligence
    from suitcode.core.quality.quality_intelligence import QualityIntelligence
    from suitcode.core.repository import Repository
    from suitcode.core.tests.test_intelligence import TestIntelligence


type WorkspaceHandle = str


class Workspace:

    def __init__(self, repository_directory: Path) -> None:
        from suitcode.core.repository import Repository

        initial_root = Repository.root_candidate(repository_directory)
        self._id = f"workspace:{initial_root.name}"
        self._repositories_by_root: dict[Path, Repository] = {}
        self.add_repository(repository_directory)

        # Import locally to avoid circular import issues.
        from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
        from suitcode.core.code.code_intelligence import CodeIntelligence
        from suitcode.core.quality.quality_intelligence import QualityIntelligence
        from suitcode.core.tests.test_intelligence import TestIntelligence

        self._code = CodeIntelligence(self)
        self._arch = ArchitectureIntelligence(self)
        self._tests = TestIntelligence(self)
        self._quality = QualityIntelligence(self)

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
        from suitcode.core.repository import Repository

        repository_root = Repository.root_candidate(repository_directory)
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

    def suit_dir_for(self, repository_directory: Path) -> Path:
        return self.get_repository(repository_directory).suit_dir

    @property
    def repository_roots(self) -> tuple[Path, ...]:
        return tuple(self._repositories_by_root.keys())

    @property
    def repositories(self) -> tuple["Repository", ...]:
        return tuple(self._repositories_by_root.values())

    @property
    def code(self) -> "CodeIntelligence":
        return self._code

    @property
    def arch(self) -> "ArchitectureIntelligence":
        return self._arch

    @property
    def tests(self) -> "TestIntelligence":
        return self._tests

    @property
    def quality(self) -> "QualityIntelligence":
        return self._quality

