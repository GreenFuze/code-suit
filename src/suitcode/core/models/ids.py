from __future__ import annotations

from pathlib import PurePosixPath

from suitcode.core.models.graph_types import NodeId


def normalize_repository_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    normalized = normalized.removeprefix("./")
    normalized = str(PurePosixPath(normalized))
    if normalized.startswith("/") or normalized == ".." or normalized.startswith("../"):
        raise ValueError("path must be repository-root relative")
    return normalized


def make_file_id(repository_rel_path: str) -> NodeId:
    rel = normalize_repository_relative_path(repository_rel_path)
    return f"file:{rel}"


def make_entity_id(
    repository_rel_path: str,
    entity_kind: str,
    entity_name: str,
    line_start: int | None = None,
    line_end: int | None = None,
) -> NodeId:
    rel = normalize_repository_relative_path(repository_rel_path)
    base = f"entity:{rel}:{entity_kind}:{entity_name}"
    if line_start is not None and line_end is not None:
        return f"{base}:{line_start}-{line_end}"
    return base
