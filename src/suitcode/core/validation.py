from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

E = TypeVar("E", bound=Exception)


def validate_timeout_seconds(
    value: int,
    *,
    min_value: int = 1,
    max_value: int = 3600,
    field_name: str = "timeout_seconds",
    error_cls: type[E] = ValueError,
) -> int:
    if value < min_value or value > max_value:
        raise error_cls(f"{field_name} must be between {min_value} and {max_value}")
    return value


def validate_preview_limit(
    value: int,
    field_name: str,
    *,
    min_value: int = 1,
    max_value: int = 50,
    error_cls: type[E] = ValueError,
) -> int:
    if value < min_value or value > max_value:
        raise error_cls(f"{field_name} must be between {min_value} and {max_value}")
    return value


def validate_change_preview_limit(
    value: int,
    field_name: str,
    *,
    min_value: int = 1,
    max_value: int = 100,
    error_cls: type[E] = ValueError,
) -> int:
    if value < min_value or value > max_value:
        raise error_cls(f"{field_name} must be between {min_value} and {max_value}")
    return value


def validate_exact_batch(
    items: Sequence[str],
    field_name: str,
    *,
    max_items: int = 25,
    error_cls: type[E] = ValueError,
) -> tuple[str, ...]:
    values = tuple(items)
    if not values:
        raise error_cls(f"{field_name} must not be empty")
    if len(values) > max_items:
        raise error_cls(f"{field_name} must not contain more than {max_items} items")
    if any(not item.strip() for item in values):
        raise error_cls(f"{field_name} must not contain empty values")
    if len(set(values)) != len(values):
        raise error_cls(f"{field_name} must not contain duplicates")
    return values
