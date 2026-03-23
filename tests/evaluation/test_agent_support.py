from suitcode.evaluation import SUPPORTED_EVALUATION_AGENTS, evaluation_agent_support
from suitcode.evaluation.metadata_models import AgentKind


def test_supported_evaluation_agents_are_explicit_and_complete() -> None:
    supported = {item.agent_kind for item in SUPPORTED_EVALUATION_AGENTS}
    assert supported == {AgentKind.CODEX, AgentKind.CLAUDE, AgentKind.CURSOR}


def test_agent_support_flags_match_phase_two_scope() -> None:
    codex = evaluation_agent_support(AgentKind.CODEX)
    claude = evaluation_agent_support(AgentKind.CLAUDE)
    cursor = evaluation_agent_support(AgentKind.CURSOR)

    assert codex.live_harness_available is True
    assert codex.passive_telemetry_available is True
    assert codex.transcript_token_estimation_available is True

    assert claude.live_harness_available is False
    assert claude.passive_telemetry_available is True
    assert claude.transcript_token_estimation_available is True
    assert any("passive telemetry" in note.lower() for note in claude.notes)

    assert cursor.live_harness_available is False
    assert cursor.passive_telemetry_available is True
    assert cursor.transcript_token_estimation_available is True
    assert any("best-effort" in note.lower() for note in cursor.notes)
