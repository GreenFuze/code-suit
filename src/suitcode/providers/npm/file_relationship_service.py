from __future__ import annotations

import json
from pathlib import Path

from suitcode.core.intelligence_models import FileRelationshipKind, FileRelationshipRef
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.provenance_builders import dependency_graph_provenance
from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver
from suitcode.providers.npm.tool_runner import TypeScriptProbeRunner


class NpmFileRelationshipService:
    _SUPPORTED_EXTENSIONS = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})

    def __init__(
        self,
        *,
        repository_root: Path,
        attachment_root: Path,
        resolver: TypeScriptLanguageServerResolver | None = None,
    ) -> None:
        self._repository_root = repository_root.expanduser().resolve()
        self._attachment_root = attachment_root.expanduser().resolve()
        self._resolver = resolver or TypeScriptLanguageServerResolver()
        self._probe_runner = TypeScriptProbeRunner(
            repository_root=self._repository_root,
            attachment_root=self._attachment_root,
            resolver=self._resolver,
        )
        self._cache: dict[str, tuple[FileRelationshipRef, ...]] = {}

    def get_file_relationships(self, repository_rel_path: str) -> tuple[FileRelationshipRef, ...]:
        normalized_path = normalize_repository_relative_path(repository_rel_path)
        if normalized_path in self._cache:
            return self._cache[normalized_path]
        absolute_path = (self._repository_root / normalized_path).resolve()
        try:
            absolute_path.relative_to(self._attachment_root)
        except ValueError:
            return tuple()
        if absolute_path.suffix.lower() not in self._SUPPORTED_EXTENSIONS:
            return tuple()
        if not absolute_path.exists() or not absolute_path.is_file():
            raise ValueError(f"file does not exist: `{normalized_path}`")

        payload = self._probe_runner.run_json_probe(
            script_name="ts_file_relationships.cjs",
            command_args=(
                str(self._repository_root),
                str(self._attachment_root),
                str(absolute_path),
                self._probe_runner.resolve_typescript_library_path(),
            ),
            error_label="TS file relationships",
        )

        relationships = self._translate_payload(normalized_path, payload)
        self._cache[normalized_path] = relationships
        return relationships

    def _translate_payload(self, repository_rel_path: str, payload: object) -> tuple[FileRelationshipRef, ...]:
        if not isinstance(payload, dict):
            raise ValueError("TypeScript relationship probe returned an invalid payload shape")
        imports = self._coerce_paths(payload.get("imports"), "imports")
        imported_by = self._coerce_paths(payload.get("imported_by"), "imported_by")
        items: list[FileRelationshipRef] = []
        for path in imports:
            items.append(
                FileRelationshipRef(
                    repository_rel_path=path,
                    relationship_kind=FileRelationshipKind.IMPORTS,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary=(
                                f"deterministic TypeScript module resolution shows `{repository_rel_path}` imports `{path}`"
                            ),
                            evidence_paths=(repository_rel_path, path),
                        ),
                    ),
                )
            )
        for path in imported_by:
            items.append(
                FileRelationshipRef(
                    repository_rel_path=path,
                    relationship_kind=FileRelationshipKind.IMPORTED_BY,
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary=(
                                f"deterministic TypeScript module resolution shows `{path}` imports `{repository_rel_path}`"
                            ),
                            evidence_paths=(repository_rel_path, path),
                        ),
                    ),
                )
            )
        return tuple(
            sorted(
                items,
                key=lambda item: (item.relationship_kind.value, item.repository_rel_path),
            )
        )

    @staticmethod
    def _coerce_paths(value: object, field_name: str) -> tuple[str, ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list):
            raise ValueError(f"TypeScript relationship probe field `{field_name}` must be a list")
        paths: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"TypeScript relationship probe field `{field_name}` must contain non-empty strings")
            normalized = normalize_repository_relative_path(item)
            if normalized not in paths:
                paths.append(normalized)
        return tuple(paths)
