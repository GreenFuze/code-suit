from __future__ import annotations

import json
import re
from pathlib import Path

from suitcode.core.provenance_builders import document_provenance
from suitcode.core.structured_artifact_models import (
    OpenApiDocumentStructure,
    OpenApiOperation,
    OpenApiSchema,
    OpenApiTag,
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})
_SUPPORTED_FILENAMES = frozenset(
    {
        "openapi.yaml",
        "openapi.yml",
        "openapi.json",
        "swagger.yaml",
        "swagger.yml",
        "swagger.json",
    }
)


def parse_openapi_document(path: Path, repository_rel_path: str) -> OpenApiDocumentStructure:
    name = path.name.lower()
    if name not in _SUPPORTED_FILENAMES:
        raise ValueError(f"unsupported OpenAPI filename: `{path.name}`")
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        return _parse_json_document(text, repository_rel_path)
    return _parse_yaml_document(text, repository_rel_path)


def _parse_json_document(text: str, repository_rel_path: str) -> OpenApiDocumentStructure:
    lines = text.splitlines()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    spec_version = _json_text(payload.get("openapi")) or _json_text(payload.get("swagger"))
    operations: list[OpenApiOperation] = []
    paths = payload.get("paths")
    if isinstance(paths, dict):
        for path_name, path_payload in paths.items():
            if not isinstance(path_name, str) or not isinstance(path_payload, dict):
                continue
            path_line = _find_json_key_line(lines, path_name)
            for method, operation_payload in path_payload.items():
                if not isinstance(method, str) or method.lower() not in _HTTP_METHODS or not isinstance(operation_payload, dict):
                    continue
                method_line = _find_json_key_line(lines, method, start_line=path_line)
                operations.append(
                    OpenApiOperation(
                        path=path_name,
                        method=method.lower(),
                        operation_id=_json_text(operation_payload.get("operationId")),
                        line_start=method_line or path_line,
                        line_end=method_line or path_line,
                    )
                )

    schemas: list[OpenApiSchema] = []
    schemas_payload = payload.get("components")
    if isinstance(schemas_payload, dict):
        schemas_obj = schemas_payload.get("schemas")
        if isinstance(schemas_obj, dict):
            for schema_name in schemas_obj:
                if not isinstance(schema_name, str):
                    continue
                line_start = _find_json_key_line(lines, schema_name)
                schemas.append(OpenApiSchema(name=schema_name, line_start=line_start, line_end=line_start))

    tags: list[OpenApiTag] = []
    tags_payload = payload.get("tags")
    if isinstance(tags_payload, list):
        for item in tags_payload:
            if not isinstance(item, dict):
                continue
            tag_name = _json_text(item.get("name"))
            if tag_name is None:
                continue
            line_start = _find_json_property_value_line(lines, "name", tag_name)
            tags.append(OpenApiTag(name=tag_name, line_start=line_start, line_end=line_start))

    provenance = (
        document_provenance(
            evidence_summary="OpenAPI document structure parsed deterministically from the specification file",
            evidence_paths=(repository_rel_path,),
            source_tool="openapi",
        ),
    )
    return OpenApiDocumentStructure(
        spec_version=spec_version,
        path_count=len({item.path for item in operations}),
        operations=tuple(operations),
        schema_count=len(schemas),
        schemas=tuple(schemas),
        tag_count=len(tags),
        tags=tuple(tags),
        provenance=provenance,
    )


def _parse_yaml_document(text: str, repository_rel_path: str) -> OpenApiDocumentStructure:
    lines = text.splitlines()
    spec_version: str | None = None
    operations: list[OpenApiOperation] = []
    schemas: list[OpenApiSchema] = []
    tags: list[OpenApiTag] = []

    section: str | None = None
    subsection: str | None = None
    current_path: str | None = None
    current_operation_index: int | None = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))

        if indent == 0:
            key, value = _parse_yaml_mapping_line(stripped)
            if key in {"openapi", "swagger"} and value is not None and spec_version is None:
                spec_version = value
            section = key
            subsection = None
            current_path = None
            current_operation_index = None
            continue

        if section == "paths":
            if indent == 2:
                key, value = _parse_yaml_mapping_line(stripped)
                current_path = key if value == "" and key.startswith("/") else None
                current_operation_index = None
                continue
            if indent == 4 and current_path is not None:
                key, value = _parse_yaml_mapping_line(stripped)
                method = key.lower()
                if value == "" and method in _HTTP_METHODS:
                    operations.append(
                        OpenApiOperation(
                            path=current_path,
                            method=method,
                            line_start=line_number,
                            line_end=line_number,
                        )
                    )
                    current_operation_index = len(operations) - 1
                    continue
            if indent >= 6 and current_operation_index is not None:
                key, value = _parse_yaml_mapping_line(stripped)
                if key == "operationId" and value is not None:
                    operations[current_operation_index] = operations[current_operation_index].model_copy(
                        update={"operation_id": value}
                    )
                continue

        if section == "components":
            if indent == 2:
                key, value = _parse_yaml_mapping_line(stripped)
                subsection = key if value == "" else None
                continue
            if subsection == "schemas" and indent == 4:
                key, value = _parse_yaml_mapping_line(stripped)
                if value == "":
                    schemas.append(OpenApiSchema(name=key, line_start=line_number, line_end=line_number))
                continue

        if section == "tags":
            if indent == 2 and stripped.startswith("- "):
                tag_name = _parse_yaml_list_mapping_value(stripped[2:], "name")
                if tag_name is not None:
                    tags.append(OpenApiTag(name=tag_name, line_start=line_number, line_end=line_number))
                continue
            if indent >= 4:
                key, value = _parse_yaml_mapping_line(stripped)
                if key == "name" and value is not None:
                    tags.append(OpenApiTag(name=value, line_start=line_number, line_end=line_number))
                continue

    provenance = (
        document_provenance(
            evidence_summary="OpenAPI document structure parsed deterministically from the specification file",
            evidence_paths=(repository_rel_path,),
            source_tool="openapi",
        ),
    )
    return OpenApiDocumentStructure(
        spec_version=spec_version,
        path_count=len({item.path for item in operations}),
        operations=tuple(operations),
        schema_count=len(schemas),
        schemas=tuple(schemas),
        tag_count=len(tags),
        tags=tuple(tags),
        provenance=provenance,
    )


def _parse_yaml_mapping_line(line: str) -> tuple[str, str | None]:
    if ":" not in line:
        return _strip_yaml_quotes(_strip_inline_comment(line).strip()), None
    key, value = line.split(":", 1)
    normalized_key = _strip_yaml_quotes(key.strip())
    normalized_value = _strip_inline_comment(value).strip()
    if not normalized_value:
        return normalized_key, ""
    return normalized_key, _strip_yaml_quotes(normalized_value)


def _parse_yaml_list_mapping_value(line: str, key: str) -> str | None:
    mapping_key, value = _parse_yaml_mapping_line(line)
    if mapping_key != key or value in {None, ""}:
        return None
    return value


def _strip_inline_comment(value: str) -> str:
    quote_char: str | None = None
    for index, char in enumerate(value):
        if char in {'"', "'"}:
            if quote_char is None:
                quote_char = char
            elif quote_char == char:
                quote_char = None
        if char == "#" and quote_char is None:
            return value[:index]
    return value


def _strip_yaml_quotes(value: str) -> str:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        return normalized[1:-1].strip()
    return normalized


def _json_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _find_json_key_line(lines: list[str], key: str, start_line: int | None = None) -> int | None:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:')
    start_index = max((start_line or 1) - 1, 0)
    for index in range(start_index, len(lines)):
        if pattern.search(lines[index]):
            return index + 1
    return None


def _find_json_property_value_line(lines: list[str], key: str, value: str) -> int | None:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"{re.escape(value)}"')
    for index, line in enumerate(lines, start=1):
        if pattern.search(line):
            return index
    return None
