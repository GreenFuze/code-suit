from __future__ import annotations

import pytest

from suitcode.providers.quality_provider_base import QualityProviderBase


def test_quality_provider_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        QualityProviderBase(repository=None)  # type: ignore[arg-type]
