from suitcode.evaluation.agent_support import evaluation_agent_support
from suitcode.evaluation.metadata_models import AgentKind

CLAUDE_EVALUATION_SUPPORT = evaluation_agent_support(AgentKind.CLAUDE)

__all__ = ["CLAUDE_EVALUATION_SUPPORT"]
