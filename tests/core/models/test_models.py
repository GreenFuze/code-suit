from __future__ import annotations

import pytest

from suitcode.core.models.graph_types import NodeKind, ProgrammingLanguage
from suitcode.core.models.nodes import EntityInfo, Evidence, FileInfo, RepositoryInfo


def test_models_forbid_extra_fields() -> None:
    with pytest.raises(Exception):
        RepositoryInfo(
            id="repo:root",
            kind=NodeKind.REPOSITORY,
            name="repo",
            root_path=".",
            unexpected=True,
        )


def test_evidence_line_range_validation() -> None:
    with pytest.raises(ValueError):
        Evidence(id="ev:1", line_start=10, line_end=2)


def test_file_and_entity_models() -> None:
    file_node = FileInfo(
        id="file:src/app.py",
        name="src/app.py",
        repository_rel_path="src/app.py",
        language=ProgrammingLanguage.PYTHON,
    )
    entity = EntityInfo(
        id="entity:src/app.py:function:main:1-3",
        name="main",
        repository_rel_path="src/app.py",
        entity_kind="function",
        line_start=1,
        line_end=3,
    )

    assert file_node.kind == NodeKind.FILE
    assert entity.kind == NodeKind.ENTITY
