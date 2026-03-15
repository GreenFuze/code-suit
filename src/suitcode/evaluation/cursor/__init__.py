from suitcode.evaluation.agent_support import evaluation_agent_support
from suitcode.evaluation.metadata_models import AgentKind

CURSOR_EVALUATION_SUPPORT = evaluation_agent_support(AgentKind.CURSOR)

__all__ = ["CURSOR_EVALUATION_SUPPORT"]
