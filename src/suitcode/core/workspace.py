from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
    from suitcode.core.code.code_intelligence import CodeIntelligence
    from suitcode.core.quality.quality_intelligence import QualityIntelligence
    from suitcode.core.tests.test_intelligence import TestIntelligence


type WorkspaceHandle = str


class Workspace:

    _VC_MARKERS = (".git", ".hg", ".svn", ".bzr")
    _IDE_MARKERS = (".vscode", ".idea")

    @classmethod
    def workspace_root_candidate(cls, repository_path: Path) -> Path:
        path = Path(repository_path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"repository path does not exist: `{repository_path}`")
        if not path.is_dir():
            raise ValueError(f"repository path is not a directory: {repository_path}")

        ancestors = [path, *path.parents]

        # Prefer the nearest ancestor that looks like a repository root.
        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._VC_MARKERS):
                return candidate

        # Fallback to nearest explicit suit root if one already exists.
        for candidate in ancestors:
            if (candidate / ".suit").is_dir():
                return candidate

        # Last heuristic when no VCS metadata exists.
        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._IDE_MARKERS):
                return candidate

        # Final fallback: use the provided directory itself.
        return path

    def __init__(self, repository_directory: Path) -> None:
        self._repositories: dict[Path, Path] = {}
        self._active_repository_root = self.add_repository(repository_directory)

        # Import locally to avoid circular import issues.
        from suitcode.core.architecture.architecture_intelligence import ArchitectureIntelligence
        from suitcode.core.code.code_intelligence import CodeIntelligence
        from suitcode.core.quality.quality_intelligence import QualityIntelligence
        from suitcode.core.tests.test_intelligence import TestIntelligence

        self._code = CodeIntelligence(self)
        self._arch = ArchitectureIntelligence(self)
        self._tests = TestIntelligence(self)
        self._quality = QualityIntelligence(self)

    @staticmethod
    def _ensure_suit_layout(repository_root: Path) -> Path:
        suit_dir = repository_root / ".suit"
        suit_dir.mkdir(parents=True, exist_ok=True)

        config_path = suit_dir / "config.json"
        state_path = suit_dir / "state.json"
        if not config_path.exists():
            config_path.write_text("{}\n", encoding="utf-8")
        if not state_path.exists():
            state_path.write_text("{}\n", encoding="utf-8")

        return suit_dir

    def add_repository(self, repository_directory: Path) -> Path:
        repository_root = self.workspace_root_candidate(repository_directory)
        if repository_root not in self._repositories:
            self._repositories[repository_root] = self._ensure_suit_layout(repository_root)
        return repository_root

    def set_active_repository(self, repository_directory: Path) -> Path:
        repository_root = self.add_repository(repository_directory)
        self._active_repository_root = repository_root
        return repository_root

    def suit_dir_for(self, repository_directory: Path) -> Path:
        repository_root = self.add_repository(repository_directory)
        return self._repositories[repository_root]

    @property
    def repository_roots(self) -> tuple[Path, ...]:
        return tuple(self._repositories.keys())

    @property
    def root(self) -> Path:
        return self._active_repository_root

    @property
    def suit_dir(self) -> Path:
        return self._repositories[self._active_repository_root]

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

