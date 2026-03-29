from __future__ import annotations

from pathlib import Path

from suitcode.providers.go import GoProvider
from suitcode.providers.markdown import MarkdownProvider
from suitcode.providers.npm import NPMProvider
from suitcode.providers.openapi import OpenApiProvider
from suitcode.providers.provider_base import ProviderBase
from suitcode.providers.provider_metadata import (
    DetectedProviderAttachment,
    DetectedProviderSupport,
    ProviderAttachmentCandidate,
    ProviderDescriptor,
    RepositorySupportResult,
)
from suitcode.providers.python import PythonProvider

BUILTIN_PROVIDER_CLASSES: tuple[type[ProviderBase], ...] = (GoProvider, MarkdownProvider, NPMProvider, OpenApiProvider, PythonProvider)


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
    normalized_root = repository_root.expanduser().resolve()
    detected: list[DetectedProviderSupport] = []

    for provider_cls in classes:
        descriptor = provider_cls.descriptor()
        attachments = _normalize_candidates(
            provider_cls.discover_attachments(normalized_root),
            descriptor,
            normalized_root,
        )
        if attachments:
            detected_roles = frozenset(
                role
                for attachment in attachments
                for role in attachment.detected_roles
            )
            detected.append(
                DetectedProviderSupport(
                    descriptor=descriptor,
                    detected_roles=detected_roles,
                    attachments=attachments,
                )
            )

    return RepositorySupportResult(
        repository_root=normalized_root,
        detected_providers=tuple(sorted(detected, key=lambda item: item.provider_id)),
    )


def _normalize_candidates(
    candidates: tuple[ProviderAttachmentCandidate, ...],
    descriptor: ProviderDescriptor,
    repository_root: Path,
) -> tuple[DetectedProviderAttachment, ...]:
    normalized: list[DetectedProviderAttachment] = []
    seen_rel_paths: set[str] = set()
    for candidate in candidates:
        if candidate.provider_id != descriptor.provider_id:
            raise ValueError(
                f"provider `{descriptor.provider_id}` returned attachment for mismatched provider id `{candidate.provider_id}`"
            )
        attachment_root = candidate.attachment_root.expanduser().resolve()
        if attachment_root != repository_root and repository_root not in attachment_root.parents:
            raise ValueError(
                f"provider `{descriptor.provider_id}` returned attachment outside repository root: `{attachment_root}`"
            )
        attachment_root_rel_path = (
            "." if attachment_root == repository_root else attachment_root.relative_to(repository_root).as_posix()
        )
        if attachment_root_rel_path in seen_rel_paths:
            raise ValueError(
                f"provider `{descriptor.provider_id}` discovered duplicate attachment root `{attachment_root_rel_path}`"
            )
        seen_rel_paths.add(attachment_root_rel_path)
        normalized.append(
            DetectedProviderAttachment(
                provider_id=descriptor.provider_id,
                attachment_root=attachment_root,
                attachment_root_rel_path=attachment_root_rel_path,
                detected_roles=frozenset(candidate.detected_roles),
                discovery_notes=tuple(candidate.discovery_notes),
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.attachment_root_rel_path))
