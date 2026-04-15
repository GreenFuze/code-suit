from __future__ import annotations

from importlib import import_module

__all__ = [
    "ArchitectureProviderBase",
    "ActionProviderBase",
    "BUILTIN_PROVIDER_CLASSES",
    "CodeProviderBase",
    "DetectedProviderSupport",
    "NPMProvider",
    "OpenApiProvider",
    "ProviderDescriptor",
    "ProviderBase",
    "ProviderRole",
    "PythonProvider",
    "QualityDiagnostic",
    "QualityEntityDelta",
    "QualityFileResult",
    "QualityProviderBase",
    "RepositorySupportResult",
    "TestProviderBase",
]

_ATTRIBUTE_MODULES = {
    "ArchitectureProviderBase": ("suitcode.providers.architecture_provider_base", "ArchitectureProviderBase"),
    "ActionProviderBase": ("suitcode.providers.action_provider_base", "ActionProviderBase"),
    "BUILTIN_PROVIDER_CLASSES": ("suitcode.providers.registry", "BUILTIN_PROVIDER_CLASSES"),
    "CodeProviderBase": ("suitcode.providers.code_provider_base", "CodeProviderBase"),
    "DetectedProviderSupport": ("suitcode.providers.provider_metadata", "DetectedProviderSupport"),
    "NPMProvider": ("suitcode.providers.npm", "NPMProvider"),
    "OpenApiProvider": ("suitcode.providers.openapi", "OpenApiProvider"),
    "ProviderDescriptor": ("suitcode.providers.provider_metadata", "ProviderDescriptor"),
    "ProviderBase": ("suitcode.providers.provider_base", "ProviderBase"),
    "ProviderRole": ("suitcode.providers.provider_roles", "ProviderRole"),
    "PythonProvider": ("suitcode.providers.python", "PythonProvider"),
    "QualityDiagnostic": ("suitcode.providers.quality_models", "QualityDiagnostic"),
    "QualityEntityDelta": ("suitcode.providers.quality_models", "QualityEntityDelta"),
    "QualityFileResult": ("suitcode.providers.quality_models", "QualityFileResult"),
    "QualityProviderBase": ("suitcode.providers.quality_provider_base", "QualityProviderBase"),
    "RepositorySupportResult": ("suitcode.providers.provider_metadata", "RepositorySupportResult"),
    "TestProviderBase": ("suitcode.providers.test_provider_base", "TestProviderBase"),
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
