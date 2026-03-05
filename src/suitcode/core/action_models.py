from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from suitcode.core.models.ids import normalize_repository_relative_path
from suitcode.core.models.nodes import StrictModel
from suitcode.core.provenance import ProvenanceEntry


class ActionKind(StrEnum):
    __test__ = False
    TEST_EXECUTION = "test_execution"
    RUNNER_EXECUTION = "runner_execution"
    BUILD_EXECUTION = "build_execution"


class ActionTargetKind(StrEnum):
    __test__ = False
    REPOSITORY = "repository"
    COMPONENT = "component"
    RUNNER = "runner"
    TEST_DEFINITION = "test_definition"


class ActionInvocation(StrictModel):
    argv: tuple[str, ...]
    cwd: str | None = None

    @field_validator("argv")
    @classmethod
    def _validate_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("argv must not be empty")
        if any(not item.strip() for item in value):
            raise ValueError("argv must not contain empty arguments")
        return value


class RepositoryAction(StrictModel):
    id: str
    name: str
    kind: ActionKind
    provider_id: str
    target_id: str
    target_kind: ActionTargetKind
    owner_ids: tuple[str, ...] = Field(default_factory=tuple)
    invocation: ActionInvocation
    dry_run_supported: bool = False
    provenance: tuple[ProvenanceEntry, ...]

    @model_validator(mode="after")
    def _validate_action(self) -> "RepositoryAction":
        if not self.id.strip():
            raise ValueError("id must not be empty")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if not self.target_id.strip():
            raise ValueError("target_id must not be empty")
        if any(not owner_id.strip() for owner_id in self.owner_ids):
            raise ValueError("owner_ids must not contain empty values")
        if len(set(self.owner_ids)) != len(self.owner_ids):
            raise ValueError("owner_ids must not contain duplicates")
        if not self.provenance:
            raise ValueError("provenance must not be empty")
        return self


class ActionQuery(StrictModel):
    repository_rel_path: str | None = None
    owner_id: str | None = None
    component_id: str | None = None
    runner_id: str | None = None
    test_id: str | None = None
    action_kinds: tuple[ActionKind, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_selector(self) -> "ActionQuery":
        selectors = [
            self.repository_rel_path is not None,
            self.owner_id is not None,
            self.component_id is not None,
            self.runner_id is not None,
            self.test_id is not None,
        ]
        if sum(selectors) > 1:
            raise ValueError(
                "exactly zero or one selector must be provided: "
                "repository_rel_path, owner_id, component_id, runner_id, test_id"
            )
        if self.repository_rel_path is not None:
            self.repository_rel_path = normalize_repository_relative_path(self.repository_rel_path)
        for field_name in ("owner_id", "component_id", "runner_id", "test_id"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if len(set(self.action_kinds)) != len(self.action_kinds):
            raise ValueError("action_kinds must not contain duplicates")
        return self
