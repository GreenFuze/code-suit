from __future__ import annotations

from suitcode.providers.action_provider_base import ActionProviderBase
from suitcode.providers.npm import NPMProvider
from suitcode.providers.python import PythonProvider


def test_npm_provider_action_contract() -> None:
    assert issubclass(NPMProvider, ActionProviderBase)


def test_python_provider_action_contract() -> None:
    assert issubclass(PythonProvider, ActionProviderBase)
