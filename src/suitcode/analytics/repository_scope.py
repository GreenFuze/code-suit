from __future__ import annotations

from pathlib import Path


def repository_roots_overlap(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    normalized_left = left.expanduser().resolve()
    normalized_right = right.expanduser().resolve()
    if normalized_left == normalized_right:
        return True
    return normalized_left in normalized_right.parents or normalized_right in normalized_left.parents


def repository_root_matches_path(repository_root: Path, candidate_root: str | Path | None) -> bool:
    if candidate_root is None:
        return False
    candidate_path = candidate_root if isinstance(candidate_root, Path) else Path(candidate_root)
    return repository_roots_overlap(repository_root, candidate_path)
