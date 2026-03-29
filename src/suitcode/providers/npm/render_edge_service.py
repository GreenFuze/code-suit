from __future__ import annotations

import json
import subprocess
from importlib import resources
from pathlib import Path

from suitcode.core.intelligence_models import RenderEdgeKind, RenderEdgeRef
from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.provenance_builders import dependency_graph_provenance
from suitcode.providers.shared.lsp import TypeScriptLanguageServerResolver


class NpmRenderEdgeService:
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
        self._cache: dict[str, tuple[RenderEdgeRef, ...]] = {}

    def get_file_render_edges(self, repository_rel_path: str) -> tuple[RenderEdgeRef, ...]:
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

        node = self._resolver.resolve_node_path()
        typescript_library = self._resolver.resolve_typescript_library_path(self._attachment_root)
        script_path = resources.files("suitcode.providers.npm").joinpath("ts_render_edges.cjs")
        command = (
            node,
            str(script_path),
            str(self._repository_root),
            str(self._attachment_root),
            str(absolute_path),
            typescript_library,
        )
        try:
            result = subprocess.run(
                command,
                cwd=self._attachment_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or "unknown TypeScript render-edge error"
            raise ValueError(f"unable to resolve deterministic TS render edges: {message}") from exc

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("TypeScript render-edge probe returned invalid JSON") from exc

        render_edges = self._translate_payload(normalized_path, payload)
        self._cache[normalized_path] = render_edges
        return render_edges

    def _translate_payload(self, repository_rel_path: str, payload: object) -> tuple[RenderEdgeRef, ...]:
        if not isinstance(payload, dict):
            raise ValueError("TypeScript render-edge probe returned an invalid payload shape")
        renders = self._coerce_edges(payload.get("renders"), "renders")
        rendered_by = self._coerce_edges(payload.get("rendered_by"), "rendered_by")
        items: list[RenderEdgeRef] = []
        for edge in renders:
            items.append(
                RenderEdgeRef(
                    repository_rel_path=edge["path"],
                    relationship_kind=RenderEdgeKind.RENDERS,
                    line_start=edge["line_start"],
                    column_start=edge["column_start"],
                    prop_names=edge["prop_names"],
                    has_spread_props=edge["has_spread_props"],
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary=(
                                f"deterministic JSX resolution shows `{repository_rel_path}` renders `{edge['path']}`"
                            ),
                            evidence_paths=(repository_rel_path, edge["path"]),
                        ),
                    ),
                )
            )
        for edge in rendered_by:
            items.append(
                RenderEdgeRef(
                    repository_rel_path=edge["path"],
                    relationship_kind=RenderEdgeKind.RENDERED_BY,
                    line_start=edge["line_start"],
                    column_start=edge["column_start"],
                    prop_names=edge["prop_names"],
                    has_spread_props=edge["has_spread_props"],
                    provenance=(
                        dependency_graph_provenance(
                            source_tool="typescript",
                            evidence_summary=(
                                f"deterministic JSX resolution shows `{edge['path']}` renders `{repository_rel_path}`"
                            ),
                            evidence_paths=(repository_rel_path, edge["path"]),
                        ),
                    ),
                )
            )
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    item.relationship_kind.value,
                    item.repository_rel_path,
                    item.line_start,
                    item.column_start,
                    item.prop_names,
                    item.has_spread_props,
                ),
            )
        )

    @staticmethod
    def _coerce_edges(value: object, field_name: str) -> tuple[dict[str, object], ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list):
            raise ValueError(f"TypeScript render-edge probe field `{field_name}` must be a list")
        items: list[dict[str, object]] = []
        seen: set[tuple[object, ...]] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain objects")
            path = item.get("path")
            line_start = item.get("line_start")
            column_start = item.get("column_start")
            prop_names = item.get("prop_names")
            has_spread_props = item.get("has_spread_props")
            if not isinstance(path, str) or not path.strip():
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain non-empty paths")
            if not isinstance(line_start, int) or line_start < 1:
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain valid line_start")
            if not isinstance(column_start, int) or column_start < 1:
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain valid column_start")
            if not isinstance(prop_names, list) or not all(isinstance(prop, str) and prop.strip() for prop in prop_names):
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain valid prop_names")
            if not isinstance(has_spread_props, bool):
                raise ValueError(f"TypeScript render-edge probe field `{field_name}` must contain valid has_spread_props")
            normalized_props: list[str] = []
            for prop in prop_names:
                normalized_prop = prop.strip()
                if normalized_prop not in normalized_props:
                    normalized_props.append(normalized_prop)
            normalized_path = normalize_repository_relative_path(path)
            dedupe_key = (
                normalized_path,
                line_start,
                column_start,
                tuple(normalized_props),
                has_spread_props,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            items.append(
                {
                    "path": normalized_path,
                    "line_start": line_start,
                    "column_start": column_start,
                    "prop_names": tuple(normalized_props),
                    "has_spread_props": has_spread_props,
                }
            )
        return tuple(items)
