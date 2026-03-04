from __future__ import annotations

import pytest

from suitcode.providers.shared.pyproject.validator import PyProjectValidator


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"project": "bad"}, "\\[project\\] must be a table"),
        ({"build-system": "bad"}, "\\[build-system\\] must be a table"),
        ({"project": {"dependencies": [1]}}, "dependencies must be an array of strings"),
        ({"project": {"scripts": {"app": 1}}}, "scripts must be a table of strings"),
    ],
)
def test_pyproject_validator_rejects_invalid_shapes(payload, message, tmp_path) -> None:
    manifest_path = tmp_path / "pyproject.toml"

    with pytest.raises(ValueError, match=message):
        PyProjectValidator().validate_root(payload, manifest_path)
