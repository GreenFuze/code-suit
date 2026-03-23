from __future__ import annotations

from pydantic import field_validator

from suitcode.analytics.models import StrictModel
from suitcode.evaluation.metadata_models import AgentKind


class EvaluationAgentSupport(StrictModel):
    agent_kind: AgentKind
    live_harness_available: bool
    passive_telemetry_available: bool
    transcript_token_estimation_available: bool
    notes: tuple[str, ...] = ()

    @field_validator("notes")
    @classmethod
    def _validate_notes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            stripped = item.strip()
            if not stripped:
                raise ValueError("notes must not contain empty values")
            normalized.append(stripped)
        return tuple(normalized)


SUPPORTED_EVALUATION_AGENTS: tuple[EvaluationAgentSupport, ...] = (
    EvaluationAgentSupport(
        agent_kind=AgentKind.CODEX,
        live_harness_available=True,
        passive_telemetry_available=True,
        transcript_token_estimation_available=True,
        notes=(
            "Codex is the only live-validated evaluation agent at this stage.",
            "Codex comparison reports are valid only when the run is not blocked by usage_limit or other infrastructure failures.",
        ),
    ),
    EvaluationAgentSupport(
        agent_kind=AgentKind.CLAUDE,
        live_harness_available=False,
        passive_telemetry_available=True,
        transcript_token_estimation_available=True,
        notes=(
            "Claude passive telemetry and transcript-estimated token summaries are available.",
            "No live Claude benchmark harness is implemented yet.",
        ),
    ),
    EvaluationAgentSupport(
        agent_kind=AgentKind.CURSOR,
        live_harness_available=False,
        passive_telemetry_available=True,
        transcript_token_estimation_available=True,
        notes=(
            "Cursor passive telemetry and transcript-estimated token summaries are available.",
            "Cursor tool-level adoption metrics remain best-effort because current native artifacts expose weaker tool traces.",
            "No live Cursor benchmark harness is implemented yet.",
        ),
    ),
)


def evaluation_agent_support(agent_kind: AgentKind) -> EvaluationAgentSupport:
    for item in SUPPORTED_EVALUATION_AGENTS:
        if item.agent_kind == agent_kind:
            return item
    raise ValueError(f"Unsupported evaluation agent: `{agent_kind}`")
