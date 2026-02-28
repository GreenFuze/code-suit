from __future__ import annotations

import pytest

from suitcode.providers.code_provider_base import CodeProviderBase


def test_code_provider_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        CodeProviderBase(repository=None)  # type: ignore[arg-type]
