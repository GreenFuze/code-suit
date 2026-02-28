from __future__ import annotations

import pytest

from suitcode.providers.test_provider_base import TestProviderBase


def test_test_provider_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        TestProviderBase(repository=None)  # type: ignore[arg-type]
