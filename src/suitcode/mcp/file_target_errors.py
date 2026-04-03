from __future__ import annotations

from pathlib import Path

from suitcode.core.repository import Repository


def explain_file_target_error(
    repository: Repository,
    repository_rel_path: str,
    message: str,
    *,
    tool_name: str,
) -> str:
    normalized = repository_rel_path.strip().replace("\\", "/").removeprefix("./")
    candidate = (repository.root / normalized).resolve()
    try:
        candidate.relative_to(repository.root)
    except ValueError:
        return message
    if not candidate.exists():
        sibling_summary = _same_directory_file_summary(repository.root, candidate.parent)
        return (
            f"repository file not found: `{normalized}`. `{tool_name}` requires an existing repository file target."
            f"{sibling_summary}"
        )
    if candidate.is_dir():
        sibling_summary = _same_directory_file_summary(repository.root, candidate)
        return (
            f"repository path `{normalized}` is a directory, not a file. `{tool_name}` requires a repository file target."
            f"{sibling_summary}"
        )
    if "unknown repository file owner" not in message:
        return message
    return (
        f"{message}. `{tool_name}` currently supports only provider-owned files. "
        "Files that exist in the repository but are not deterministically owned by a registered provider, "
        "including unsupported plain-text or documentation artifacts, are not supported by this tool."
    )


def _same_directory_file_summary(repository_root: Path, directory: Path) -> str:
    try:
        directory.relative_to(repository_root)
    except ValueError:
        return ""
    if not directory.exists() or not directory.is_dir():
        return ""
    sibling_files = sorted(item.name for item in directory.iterdir() if item.is_file())[:8]
    if not sibling_files:
        return ""
    directory_label = directory.relative_to(repository_root).as_posix()
    rendered = ", ".join(f"`{item}`" for item in sibling_files)
    return f" Exact file siblings in `{directory_label}`: {rendered}."
