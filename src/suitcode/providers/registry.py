from __future__ import annotations

from pathlib import Path

from suitcode.providers.npm import NPMProvider
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.provider_metadata import (
    DetectedProviderSupport,
    ProviderDescriptor,
    RepositorySupportResult,
)
from suitcode.providers.python import PythonProvider


BUILTIN_PROVIDER_CLASSES: tuple[type[ProviderBase], ...] = (NPMProvider, PythonProvider)


def _normalize_provider_classes(
    provider_classes: tuple[type[ProviderBase], ...] | None = None,
) -> tuple[type[ProviderBase], ...]:
    classes = provider_classes or BUILTIN_PROVIDER_CLASSES
    if not classes:
        raise ValueError("provider registry is empty")

    seen_ids: set[str] = set()
    for provider_cls in classes:
        descriptor = provider_cls.descriptor()
        if descriptor.provider_id in seen_ids:
            raise ValueError(f"duplicate provider id in registry: `{descriptor.provider_id}`")
        seen_ids.add(descriptor.provider_id)

    return classes


def get_provider_descriptors(
    provider_classes: tuple[type[ProviderBase], ...] | None = None,
) -> tuple[ProviderDescriptor, ...]:
    classes = _normalize_provider_classes(provider_classes)
    return tuple(provider_cls.descriptor() for provider_cls in classes)


def detect_support_for_root(
    repository_root: Path,
    provider_classes: tuple[type[ProviderBase], ...] | None = None,
) -> RepositorySupportResult:
    classes = _normalize_provider_classes(provider_classes)
    detected: list[DetectedProviderSupport] = []

    for provider_cls in classes:
        roles = provider_cls.detect_roles(repository_root)
        if roles:
            detected.append(
                DetectedProviderSupport(
                    descriptor=provider_cls.descriptor(),
                    detected_roles=frozenset(roles),
                )
            )

    return RepositorySupportResult(
        repository_root=repository_root,
        detected_providers=tuple(detected),
    )
