from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar

from suitcode.core.models import normalize_repository_relative_path

_EntityT = TypeVar("_EntityT")


@dataclass(frozen=True)
class ResolvedRepositoryFile:
    path: Path
    repository_rel_path: str


@dataclass(frozen=True)
class FileSnapshot(Generic[_EntityT]):
    content_sha: str
    entities: tuple[_EntityT, ...]


class QualityFilePipeline(Generic[_EntityT]):
    def __init__(
        self,
        repository_root: Path,
        entity_reader: Callable[[str], tuple[_EntityT, ...]],
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._entity_reader = entity_reader

    def resolve_file(self, repository_rel_path: str) -> ResolvedRepositoryFile:
        normalized = normalize_repository_relative_path(repository_rel_path)
        file_path = (self._repository_root / normalized).resolve()
        try:
            file_path.relative_to(self._repository_root)
        except ValueError as exc:
            raise ValueError(f"path escapes repository root: `{repository_rel_path}`") from exc
        if not file_path.exists():
            raise ValueError(f"file does not exist: `{repository_rel_path}`")
        if not file_path.is_file():
            raise ValueError(f"path is not a file: `{repository_rel_path}`")
        return ResolvedRepositoryFile(path=file_path, repository_rel_path=normalized)

    def capture_snapshot(self, resolved_file: ResolvedRepositoryFile) -> FileSnapshot[_EntityT]:
        return FileSnapshot(
            content_sha=self._file_sha(resolved_file.path),
            entities=self._entity_reader(resolved_file.repository_rel_path),
        )

    @staticmethod
    def _file_sha(file_path: Path) -> str:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()
