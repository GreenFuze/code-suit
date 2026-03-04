from __future__ import annotations

from pydantic import field_validator, model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel


class SymbolLookupTarget(StrictModel):
    symbol_id: str | None = None
    repository_rel_path: str | None = None
    line: int | None = None
    column: int | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "SymbolLookupTarget":
        has_symbol_id = self.symbol_id is not None
        has_location = (
            self.repository_rel_path is not None
            or self.line is not None
            or self.column is not None
        )
        if has_symbol_id == has_location:
            raise ValueError(
                "exactly one target mode must be used: either symbol_id or repository_rel_path+line+column"
            )
        if has_symbol_id:
            if not self.symbol_id.strip():
                raise ValueError("symbol_id must not be empty")
            return self
        if self.repository_rel_path is None or self.line is None or self.column is None:
            raise ValueError("repository_rel_path, line, and column are required for location lookups")
        self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        return self

    @field_validator("line", "column")
    @classmethod
    def _validate_positive(cls, value: int | None, info) -> int | None:
        if value is not None and value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value


class CodeLocation(StrictModel):
    repository_rel_path: str
    line_start: int
    line_end: int | None = None
    column_start: int
    column_end: int | None = None
    symbol_id: str | None = None

    @field_validator("repository_rel_path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return normalize_repository_relative_path(value)

    @field_validator("line_start", "column_start")
    @classmethod
    def _validate_required_positive(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1")
        return value

    @field_validator("line_end")
    @classmethod
    def _validate_line_end(cls, value: int | None, info) -> int | None:
        line_start = info.data.get("line_start")
        if value is not None:
            if value < 1:
                raise ValueError("line_end must be >= 1")
            if line_start is not None and value < line_start:
                raise ValueError("line_end must be >= line_start")
        return value

    @field_validator("column_end")
    @classmethod
    def _validate_column_end(cls, value: int | None, info) -> int | None:
        column_start = info.data.get("column_start")
        if value is not None:
            if value < 1:
                raise ValueError("column_end must be >= 1")
            if column_start is not None and value < column_start:
                raise ValueError("column_end must be >= column_start")
        return value
