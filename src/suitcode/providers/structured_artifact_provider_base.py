from __future__ import annotations

from abc import ABC, abstractmethod

from suitcode.core.structured_artifact_models import StructuredArtifact
from suitcode.providers.provider_base import ProviderBase


class StructuredArtifactProviderBase(ProviderBase, ABC):
    @abstractmethod
    def describe_structured_artifact(self, repository_rel_path: str) -> StructuredArtifact | None:
        raise NotImplementedError
