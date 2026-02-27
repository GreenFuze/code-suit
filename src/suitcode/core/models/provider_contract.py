from __future__ import annotations

import re

from suitcode.core.models.errors import GraphScopeError


SCOPE_PATTERN = re.compile(r"^provider:[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+$")


def validate_scope(scope: str) -> None:
    if not SCOPE_PATTERN.fullmatch(scope):
        raise GraphScopeError(
            f"invalid scope format: {scope}",
            remediation="Use 'provider:<name>:<profile>' scope format.",
        )
