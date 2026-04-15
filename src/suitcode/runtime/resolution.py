from __future__ import annotations

from pathlib import Path

from suitcode.runtime.models import ServerFamily


def server_family_for_resolver(resolver: object) -> ServerFamily | None:
    resolver_module = resolver.__class__.__module__
    resolver_name = resolver.__class__.__name__
    if resolver_module == "suitcode.providers.go.lsp_resolution" and resolver_name == "GoplsResolver":
        return ServerFamily.GOPLS
    if resolver_module == "suitcode.providers.python.lsp_resolution" and resolver_name == "BasedPyrightResolver":
        return ServerFamily.BASEDPYRIGHT
    if resolver_module == "suitcode.providers.shared.lsp.resolver" and resolver_name == "TypeScriptLanguageServerResolver":
        return ServerFamily.TYPESCRIPT_LANGUAGE_SERVER
    return None


def resolve_command_for_family(family: ServerFamily, attachment_root: Path) -> tuple[tuple[str, ...], dict[str, object] | None]:
    root = attachment_root.expanduser().resolve()
    resolver = _resolver_for_family(family)
    command = resolver.resolve(root)
    initialization_options = (
        resolver.resolve_initialization_options(root)
        if hasattr(resolver, "resolve_initialization_options")
        else None
    )
    return command, initialization_options


def provider_id_to_server_family(provider_id: str) -> ServerFamily | None:
    normalized = provider_id.strip()
    if normalized == "go":
        return ServerFamily.GOPLS
    if normalized == "python":
        return ServerFamily.BASEDPYRIGHT
    if normalized == "npm":
        return ServerFamily.TYPESCRIPT_LANGUAGE_SERVER
    return None


def _resolver_for_family(family: ServerFamily) -> object:
    if family == ServerFamily.GOPLS:
        from suitcode.providers.go.lsp_resolution import GoplsResolver

        return GoplsResolver()
    if family == ServerFamily.BASEDPYRIGHT:
        from suitcode.providers.python.lsp_resolution import BasedPyrightResolver

        return BasedPyrightResolver()
    if family == ServerFamily.TYPESCRIPT_LANGUAGE_SERVER:
        from suitcode.providers.shared.lsp.resolver import TypeScriptLanguageServerResolver

        return TypeScriptLanguageServerResolver()
    raise ValueError(f"unsupported server family `{family.value}`")
