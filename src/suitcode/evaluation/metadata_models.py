from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from suitcode.analytics.models import StrictModel


class AgentKind(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"
    CURSOR = "cursor"


class AgentRunMetadata(StrictModel):
    agent_kind: AgentKind
    cli_name: str
    cli_version: str | None = None
    model_name: str | None = None
    model_provider: str | None = None
    host_os: str
    working_directory: str
    command_prefix: tuple[str, ...] = ()
    profile_name: str | None = None
    config_overrides: tuple[str, ...] = ()
    full_auto: bool | None = None
    sandbox_mode: str | None = None
    bypass_approvals_and_sandbox: bool | None = None
    suitcode_enabled: bool | None = None
    mcp_transport: str | None = None
    git_commit_hash: str | None = None
    git_branch: str | None = None
    git_repository_url: str | None = None

    @field_validator(
        "cli_name",
        "cli_version",
        "model_name",
        "model_provider",
        "host_os",
        "working_directory",
        "profile_name",
        "mcp_transport",
        "git_commit_hash",
        "git_branch",
        "git_repository_url",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("metadata text fields must not be empty")
        return stripped

    @field_validator("command_prefix", "config_overrides")
    @classmethod
    def _validate_sequences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("metadata sequences must not contain empty values")
            normalized.append(stripped)
        return tuple(normalized)
