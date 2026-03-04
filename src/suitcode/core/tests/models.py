from __future__ import annotations

from pydantic import model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel, TestDefinition


class RelatedTestTarget(StrictModel):
    repository_rel_path: str | None = None
    owner_id: str | None = None

    @model_validator(mode="after")
    def _validate_target_mode(self) -> "RelatedTestTarget":
        has_path = self.repository_rel_path is not None
        has_owner = self.owner_id is not None
        if has_path == has_owner:
            raise ValueError("exactly one of repository_rel_path or owner_id must be provided")
        if has_path:
            self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        elif self.owner_id is not None and not self.owner_id.strip():
            raise ValueError("owner_id must not be empty")
        return self


class RelatedTestMatch(StrictModel):
    test_definition: TestDefinition
    relation_reason: str
    matched_owner_id: str | None = None
    matched_repository_rel_path: str | None = None

    @model_validator(mode="after")
    def _validate_reason_and_match(self) -> "RelatedTestMatch":
        allowed = {"same_owner", "same_component", "same_package", "repository_default_suite"}
        if self.relation_reason not in allowed:
            raise ValueError(f"unsupported relation_reason: `{self.relation_reason}`")
        if self.matched_repository_rel_path is not None:
            self.matched_repository_rel_path = normalize_repository_relative_path(self.matched_repository_rel_path)
        return self
