from __future__ import annotations

from importlib import import_module

__all__ = ["Repository", "Workspace", "WorkspaceHandle"]

_ATTRIBUTE_MODULES = {
    "Repository": ("suitcode.core.repository", "Repository"),
    "Workspace": ("suitcode.core.workspace", "Workspace"),
    "WorkspaceHandle": ("suitcode.core.workspace", "WorkspaceHandle"),
}


def __getattr__(name: str):
    target = _ATTRIBUTE_MODULES.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
