from __future__ import annotations

from suitcode.evaluation.metadata_models import AgentKind, AgentRunMetadata


def test_agent_run_metadata_supports_all_planned_agents() -> None:
    for agent_kind in (AgentKind.CODEX, AgentKind.CLAUDE, AgentKind.CURSOR):
        metadata = AgentRunMetadata(
            agent_kind=agent_kind,
            cli_name=f"{agent_kind.value}-cli",
            cli_version="1.0.0",
            model_name="demo-model",
            model_provider="demo-provider",
            host_os="Windows-11",
            working_directory="C:/repo",
            command_prefix=("agent", "exec"),
            config_overrides=("features.demo=true",),
            full_auto=False,
            sandbox_mode="danger-full-access",
            bypass_approvals_and_sandbox=True,
            suitcode_enabled=(agent_kind == AgentKind.CODEX),
            mcp_transport=("stdio" if agent_kind == AgentKind.CODEX else None),
            git_commit_hash="abc123",
            git_branch="main",
            git_repository_url="git@example.com:demo/repo.git",
        )
        assert metadata.agent_kind == agent_kind
        assert metadata.cli_name == f"{agent_kind.value}-cli"
