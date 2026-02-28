from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suitcode.core.workspace import Workspace


class Repository:
    _VC_MARKERS = (".git", ".hg", ".svn", ".bzr")
    _IDE_MARKERS = (".vscode", ".idea")

    @classmethod
    def root_candidate(cls, repository_path: Path) -> Path:
        path = Path(repository_path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"repository path does not exist: `{repository_path}`")
        if not path.is_dir():
            raise ValueError(f"repository path is not a directory: {repository_path}")

        ancestors = [path, *path.parents]

        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._VC_MARKERS):
                return candidate

        for candidate in ancestors:
            if (candidate / ".suit").is_dir():
                return candidate

        for candidate in ancestors:
            if any((candidate / marker).exists() for marker in cls._IDE_MARKERS):
                return candidate

        return path

    @staticmethod
    def ensure_suit_layout(repository_root: Path) -> Path:
        suit_dir = repository_root / ".suit"
        suit_dir.mkdir(parents=True, exist_ok=True)

        config_path = suit_dir / "config.json"
        state_path = suit_dir / "state.json"
        if not config_path.exists():
            config_path.write_text("{}\n", encoding="utf-8")
        if not state_path.exists():
            state_path.write_text("{}\n", encoding="utf-8")

        return suit_dir

    def __init__(self, workspace: Workspace, repository_directory: Path, repository_id: str) -> None:
        self._workspace = workspace
        self._root = self.root_candidate(repository_directory)
        self._suit_dir = self.ensure_suit_layout(self._root)
        self._id = repository_id

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    @property
    def id(self) -> str:
        return self._id

    @property
    def root(self) -> Path:
        return self._root

    @property
    def suit_dir(self) -> Path:
        return self._suit_dir

    @property
    def name(self) -> str:
        return self._root.name
