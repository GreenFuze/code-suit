from __future__ import annotations

import pytest

from suitcode.providers.shared.quality_file_pipeline import QualityFilePipeline


def test_quality_file_pipeline_resolves_and_snapshots_file(tmp_path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    target = repository_root / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('ok')\n", encoding="utf-8")
    captured_paths: list[str] = []

    def _entity_reader(repository_rel_path: str) -> tuple[str, ...]:
        captured_paths.append(repository_rel_path)
        return ("entity:a",)

    pipeline = QualityFilePipeline(repository_root, entity_reader=_entity_reader)
    resolved = pipeline.resolve_file("src/main.py")
    snapshot = pipeline.capture_snapshot(resolved)

    assert resolved.repository_rel_path == "src/main.py"
    assert resolved.path == target
    assert snapshot.content_sha
    assert snapshot.entities == ("entity:a",)
    assert captured_paths == ["src/main.py"]


def test_quality_file_pipeline_fails_fast_for_invalid_path(tmp_path) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(parents=True)
    pipeline = QualityFilePipeline(repository_root, entity_reader=lambda _: tuple())

    with pytest.raises(ValueError, match="file does not exist"):
        pipeline.resolve_file("missing.py")

    with pytest.raises(ValueError, match="repository-root relative|path escapes repository root"):
        pipeline.resolve_file("../outside.py")
